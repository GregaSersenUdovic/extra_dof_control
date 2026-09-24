#!/usr/bin/env python3

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node

from extra_dof_control.action import MoveAxis


class AxisClient(Node):

    def __init__(self):
        super().__init__('extra_dof_action_client')

        self._client = ActionClient(
            self,
            MoveAxis,
            '/extra_dof/move_axis',
        )

    def send_goal(self, preset_index):
        try:
            preset_index = int(preset_index)
        except (TypeError, ValueError):
            self.get_logger().error(
                f'Invalid preset index: {preset_index!r}'
            )
            return False

        if preset_index not in (0, 1, 2):
            self.get_logger().error(
                f'Invalid preset index {preset_index}. '
                'Allowed values are 0, 1, 2.'
            )
            return False

        self.get_logger().info(
            'Waiting for extra DOF ActionServer...'
        )

        if not self._client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error(
                'Extra DOF ActionServer not available.'
            )
            return False

        goal = MoveAxis.Goal()
        goal.preset_index = preset_index

        self.get_logger().info(
            f'Sending preset: {preset_index}'
        )

        future = self._client.send_goal_async(
            goal,
            feedback_callback=self.feedback_callback,
        )

        rclpy.spin_until_future_complete(self, future)

        if future.exception() is not None:
            self.get_logger().error(
                f'Failed to send goal: {future.exception()}'
            )
            return False

        goal_handle = future.result()

        if goal_handle is None or not goal_handle.accepted:
            self.get_logger().error('Goal rejected.')
            return False

        result_future = goal_handle.get_result_async()

        rclpy.spin_until_future_complete(
            self,
            result_future,
        )

        if result_future.exception() is not None:
            self.get_logger().error(
                f'Failed to receive result: '
                f'{result_future.exception()}'
            )
            return False

        result = result_future.result().result

        self.get_logger().info(
            f'Result: success={result.success}, '
            f'position={result.final_position_mm:.3f} mm, '
            f'message="{result.message}"'
        )

        return bool(result.success)

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback

        self.get_logger().info(
            f'Position: {feedback.current_position_mm:.3f} mm | '
            f'Error: {feedback.error_mm:+.3f} mm'
        )


def main(args=None):
    rclpy.init(args=args)

    node = AxisClient()

    try:
        node.send_goal(1)
    finally:
        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
