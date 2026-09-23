#!/usr/bin/env python3

import threading
import time

import rclpy

from rclpy.action import (
    ActionServer,
    CancelResponse,
    GoalResponse,
)
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from rcl_interfaces.srv import GetParameters
from std_msgs.msg import Float64

from extra_dof_control.action import MoveAxis


class AxisActionServer(Node):

    def __init__(self):
        super().__init__(
            'extra_dof_action_server',
            namespace='extra_dof',
        )
        self.declare_parameter(
            'target_topic',
            '/revpi_closed_loop_motor_node/target_mm',
        )
        self.declare_parameter(
            'position_topic',
            '/revpi_closed_loop_motor_node/position_mm',
        )
        self.declare_parameter('tolerance_mm', 0.2)
        self.declare_parameter('move_timeout_s', 30.0)
        self.declare_parameter('feedback_timeout_s', 1.0)
        self.declare_parameter('min_position_mm', 46.0)
        self.declare_parameter('max_position_mm', 290.0)

        self.target_topic = str(
            self.get_parameter('target_topic').value
        )
        self.position_topic = str(
            self.get_parameter('position_topic').value
        )
        self.tolerance_mm = float(
            self.get_parameter('tolerance_mm').value
        )
        self.move_timeout_s = float(
            self.get_parameter('move_timeout_s').value
        )
        self.feedback_timeout_s = float(
            self.get_parameter('feedback_timeout_s').value
        )
        self.min_position_mm = float(
            self.get_parameter('min_position_mm').value
        )
        self.max_position_mm = float(
            self.get_parameter('max_position_mm').value
        )

        self.current_position_mm = None
        self.last_position_time = None

        self.state_lock = threading.Lock()
        self.goal_active = False

        self.callback_group = ReentrantCallbackGroup()

        self.target_pub = self.create_publisher(
            Float64,
            self.target_topic,
            10,
        )

        self.position_sub = self.create_subscription(
            Float64,
            self.position_topic,
            self.position_callback,
            qos_profile_sensor_data,
            callback_group=self.callback_group,
        )

        self.preset_client = self.create_client(
            GetParameters,
            '/revpi_closed_loop_motor_node/get_parameters',
            callback_group=self.callback_group,
        )

        self.action_server = ActionServer(
            self,
            MoveAxis,
            'move_axis',
            execute_callback=self.execute_callback,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback,
            callback_group=self.callback_group,
        )

        self.get_logger().info(
            f'Extra DOF Action Server ready. '
            f'Range: {self.min_position_mm:.1f}-'
            f'{self.max_position_mm:.1f} mm, '
            f'tolerance: {self.tolerance_mm:.2f} mm. '
            f'Preset indices: 0, 1, 2.'
        )

    def position_callback(self, msg):
        with self.state_lock:
            self.current_position_mm = float(msg.data)
            self.last_position_time = time.monotonic()

    def get_position_state(self):
        with self.state_lock:
            return (
                self.current_position_mm,
                self.last_position_time,
            )

    def hold_position(self, position):
        if position is not None:
            self.target_pub.publish(
                Float64(data=float(position))
            )

    @staticmethod
    def preset_index(value):
        if value in (0.0, 1.0, 2.0):
            return int(value)
        return None

    def get_preset_target(self, preset_index):
        if not self.preset_client.wait_for_service(
            timeout_sec=2.0
        ):
            return None

        request = GetParameters.Request()
        request.names = [f'preset_{preset_index}']

        future = self.preset_client.call_async(request)

        deadline = time.monotonic() + 2.0

        while (
            rclpy.ok()
            and not future.done()
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)

        if (
            not future.done()
            or future.exception() is not None
        ):
            return None

        response = future.result()

        if response is None or len(response.values) != 1:
            return None

        return float(response.values[0].double_value)

    def goal_callback(self, goal_request):
        requested = float(goal_request.target_mm)

        is_preset = self.preset_index(requested) is not None

        if (
            not is_preset
            and not (
                self.min_position_mm
                <= requested
                <= self.max_position_mm
            )
        ):
            self.get_logger().error(
                f'Rejecting target {requested:.3f}. '
                f'Use preset index 0, 1, 2 or a position '
                f'between {self.min_position_mm:.3f} and '
                f'{self.max_position_mm:.3f} mm.'
            )
            return GoalResponse.REJECT

        with self.state_lock:
            if self.goal_active:
                self.get_logger().warn(
                    'Rejecting new goal because another '
                    'axis move is already active.'
                )
                return GoalResponse.REJECT

            self.goal_active = True

        return GoalResponse.ACCEPT

    def cancel_callback(self, goal_handle):
        self.get_logger().warn(
            'Axis movement cancellation requested.'
        )
        return CancelResponse.ACCEPT

    def execute_callback(self, goal_handle):
        requested = float(
            goal_handle.request.target_mm
        )

        result = MoveAxis.Result()

        try:
            preset = self.preset_index(requested)

            if preset is not None:
                target_mm = self.get_preset_target(preset)

                if target_mm is None:
                    position, _ = self.get_position_state()

                    result.success = False
                    result.final_position_mm = (
                        position
                        if position is not None
                        else float('nan')
                    )
                    result.message = (
                        f'Could not read preset_{preset} '
                        f'from motor controller.'
                    )

                    goal_handle.abort()
                    return result

                self.get_logger().info(
                    f'Preset {preset} resolved to '
                    f'{target_mm:.3f} mm.'
                )
            else:
                target_mm = requested

            if self.target_pub.get_subscription_count() == 0:
                position, _ = self.get_position_state()

                result.success = False
                result.final_position_mm = (
                    position
                    if position is not None
                    else float('nan')
                )
                result.message = (
                    'Motor controller is not available.'
                )

                goal_handle.abort()
                return result

            feedback_deadline = (
                time.monotonic()
                + self.feedback_timeout_s
            )

            while (
                rclpy.ok()
                and time.monotonic() < feedback_deadline
            ):
                position, last_time = self.get_position_state()

                if (
                    position is not None
                    and last_time is not None
                    and (
                        time.monotonic() - last_time
                        <= self.feedback_timeout_s
                    )
                ):
                    break

                time.sleep(0.02)

            else:
                result.success = False
                result.final_position_mm = float('nan')
                result.message = (
                    'No fresh encoder feedback available.'
                )

                goal_handle.abort()
                return result

            self.target_pub.publish(
                Float64(data=target_mm)
            )

            self.get_logger().info(
                f'Axis target sent: {target_mm:.3f} mm'
            )

            start_time = time.monotonic()
            stable_samples = 0

            while rclpy.ok():
                position, last_time = self.get_position_state()

                if goal_handle.is_cancel_requested:
                    self.hold_position(position)

                    result.success = False
                    result.final_position_mm = (
                        position
                        if position is not None
                        else float('nan')
                    )
                    result.message = 'Movement cancelled.'

                    goal_handle.canceled()
                    return result

                now = time.monotonic()

                if (
                    last_time is None
                    or now - last_time
                    > self.feedback_timeout_s
                ):
                    result.success = False
                    result.final_position_mm = (
                        position
                        if position is not None
                        else float('nan')
                    )
                    result.message = (
                        'Encoder feedback became stale.'
                    )

                    goal_handle.abort()
                    return result

                error_mm = target_mm - position

                feedback = MoveAxis.Feedback()
                feedback.current_position_mm = position
                feedback.error_mm = error_mm
                goal_handle.publish_feedback(feedback)

                if abs(error_mm) <= self.tolerance_mm:
                    stable_samples += 1
                else:
                    stable_samples = 0

                if stable_samples >= 5:
                    result.success = True
                    result.final_position_mm = position

                    if preset is not None:
                        result.message = (
                            f'Preset {preset} reached.'
                        )
                    else:
                        result.message = 'Target reached.'

                    self.get_logger().info(
                        f'Axis reached {position:.3f} mm '
                        f'(error {error_mm:+.3f} mm).'
                    )

                    goal_handle.succeed()
                    return result

                if (
                    now - start_time
                    > self.move_timeout_s
                ):
                    self.hold_position(position)

                    result.success = False
                    result.final_position_mm = position
                    result.message = (
                        f'Movement timed out after '
                        f'{self.move_timeout_s:.1f} s.'
                    )

                    goal_handle.abort()
                    return result

                time.sleep(0.02)

        finally:
            with self.state_lock:
                self.goal_active = False


def main(args=None):
    rclpy.init(args=args)

    node = AxisActionServer()

    executor = MultiThreadedExecutor(
        num_threads=2
    )
    executor.add_node(node)

    try:
        executor.spin()

    except KeyboardInterrupt:
        pass

    finally:
        executor.shutdown()
        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
