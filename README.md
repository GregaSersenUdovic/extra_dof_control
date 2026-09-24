# extra_dof_control

ROS 2 Humble Action interface for controlling an additional linear degree of freedom driven by a RevPi-based motor controller.

The Action interface is intentionally limited to **three fixed presets**, corresponding to the three screwdriver positions used by the system. Arbitrary millimetre targets are not exposed through the Action interface.

The system uses:

- **RevPi Connect 4 + RevPi MIO** for motor control
- **TB6600-class stepper driver**
- **LA11 absolute encoder** connected to a Raspberry Pi
- **ROS 2 Humble**
- A closed-loop motor node on the RevPi
- A ROS 2 ActionServer exposed as `/extra_dof/move_axis`

The RevPi motor controller and ActionServer are configured to start automatically through `systemd`. The LA11 encoder node on the Raspberry Pi is also intended to start automatically.

---

## ROS 2 network

Current ROS domain:

```bash
export ROS_DOMAIN_ID=42
export ROS_LOCALHOST_ONLY=0
```

All ROS 2 devices participating in this system must use the same `ROS_DOMAIN_ID`.

### RevPi ROS domain configuration

The RevPi startup scripts currently containing the domain setting are:

```text
/home/pi/ros2_ws/start_extra_dof_action_server.sh
/home/pi/ros2_ws/start_linear_motor.sh
```

After changing the domain ID, restart:

```bash
sudo systemctl restart linear-motor.service
sudo systemctl restart extra-dof-action-server.service
```

### Raspberry Pi ROS domain configuration

The Raspberry Pi encoder startup script is:

```text
/ros2_ws/start_la11_encoder.sh
```

The handover notes currently reference the following service:

```bash
sudo systemctl restart la11-encoder.service
```

If that service name differs on the Raspberry Pi, verify it with:

```bash
systemctl list-units --type=service | grep -Ei 'la11|encoder'
```

---

## Network layout

The RevPi PC-facing Ethernet interface uses DHCP, so its IP address may change when connected to another computer or network.

For SSH, use mDNS where available:

```bash
ssh pi@RevPi160200.local
```

The Raspberry Pi is connected to the RevPi through a separate internal network and normally does not need to be accessed directly from the control PC.

---

## Automatic startup

The following components should start automatically:

```text
RevPi:
- linear-motor.service
- extra-dof-action-server.service

Raspberry Pi:
- LA11 encoder service
```

Because of this, manual Docker/node startup commands are normally **not needed during normal operation**.

To check service status on the RevPi:

```bash
sudo systemctl status linear-motor.service --no-pager -l
sudo systemctl status extra-dof-action-server.service --no-pager -l
```

---

## Main ROS interfaces

### Action

```text
/extra_dof/move_axis
```

Action type:

```text
extra_dof_control/action/MoveAxis
```

Current action definition:

```text
uint8 preset_index
---
bool success
float64 final_position_mm
string message
---
float64 current_position_mm
float64 error_mm
```

The Action accepts only preset indices:

```text
0 -> preset_0
1 -> preset_1
2 -> preset_2
```

Any other preset index is rejected.

### Motor node topics

```text
/revpi_closed_loop_motor_node/target_mm
/revpi_closed_loop_motor_node/position_mm
/revpi_closed_loop_motor_node/preset
```

For normal external control, use the **Action interface**. The motor-node topics are low-level interfaces used internally and for diagnostics.

---

## Preset positions

The ActionServer does not duplicate the physical preset positions. It reads them from the closed-loop motor node using ROS parameters.

Current defaults:

```text
preset_0 = 59.0 mm
preset_1 = 168.0 mm
preset_2 = 277.0 mm
```

The Action flow is:

```text
preset index
    ↓
ActionServer
    ↓
read preset_N from the closed-loop motor node
    ↓
publish resolved target in mm
    ↓
closed-loop motor controller
    ↓
LA11 encoder feedback
    ↓
Action feedback/result
```

The closed-loop motor node still contains its own minimum and maximum target limits for low-level motor safety:

```text
min_target_mm = 46.0
max_target_mm = 290.0
```

These limits are not part of the public Action command interface because the Action accepts presets only.

---

## Quick PC setup

On the control PC:

```bash
export ROS_DOMAIN_ID=42
export ROS_LOCALHOST_ONLY=0
```

Check that the ActionServer is visible:

```bash
ROS2CLI_NO_DAEMON=1 ros2 action info /extra_dof/move_axis
```

Expected:

```text
Action servers: 1
```

You can also list actions:

```bash
ROS2CLI_NO_DAEMON=1 ros2 action list -t
```

---

## Action tests

### Preset 0

```bash
ros2 action send_goal   /extra_dof/move_axis   extra_dof_control/action/MoveAxis   "{preset_index: 0}"   --feedback
```

### Preset 1

```bash
ros2 action send_goal   /extra_dof/move_axis   extra_dof_control/action/MoveAxis   "{preset_index: 1}"   --feedback
```

### Preset 2

```bash
ros2 action send_goal   /extra_dof/move_axis   extra_dof_control/action/MoveAxis   "{preset_index: 2}"   --feedback
```

### Invalid preset rejection test

```bash
ros2 action send_goal   /extra_dof/move_axis   extra_dof_control/action/MoveAxis   "{preset_index: 3}"   --feedback
```

The goal should be rejected and the motor should not move.

---

## Action feedback and completion

During a move, the ActionServer publishes:

```text
current_position_mm
error_mm
```

The position is derived from:

```text
/la11_encoder_node/position_mm
    ↓
/revpi_closed_loop_motor_node/position_mm
    ↓
ActionServer
```

The ActionServer reports success only after the measured position remains within its tolerance for multiple consecutive samples.

The server also checks for stale encoder feedback and supports Action cancellation. On cancellation, it commands the current measured position as the new target so the low-level controller stops pursuing the old target.

---

## Live position monitoring

The preferred PC-side position topic is:

```text
/revpi_closed_loop_motor_node/position_mm
```

Monitor it with:

```bash
ROS2CLI_NO_DAEMON=1 ros2 topic echo   /revpi_closed_loop_motor_node/position_mm   --qos-reliability best_effort
```

The raw LA11 encoder topic is:

```text
/la11_encoder_node/position_mm
```

The Raspberry Pi is on a separate network behind the RevPi, so the raw encoder topic may not always be directly discoverable from the control PC.

---

## Reusable ActionClient

Other ROS 2 Python packages can import the client with:

```python
from extra_dof_py.axis_client import AxisClient
```

Example:

```python
client = AxisClient()

# Move to preset 1
success = client.send_goal(1)
```

Valid values are:

```text
0
1
2
```

The ActionClient sends commands to:

```text
/extra_dof/move_axis
```

The ActionServer runs on the RevPi.

---


## Important: deploying ActionServer changes to the RevPi

The `axis_server.py` file in this repository is the source copy of the ActionServer and is provided for version control, review, and reuse.

Changing the file on the control PC or on GitHub **does not automatically update the ActionServer that is running on the RevPi**.

For changes to take effect on the physical system, update the RevPi copy:

```text
/home/pi/ros2_ws/src/extra_dof_control/extra_dof_py/axis_server.py
```

The corresponding path inside the ROS 2 Docker container is:

```text
/ros2_ws/src/extra_dof_control/extra_dof_py/axis_server.py
```

After changing or copying the server file onto the RevPi, rebuild the package inside the RevPi ROS 2 container:

```bash
cd /ros2_ws
source /opt/ros/humble/setup.bash

colcon build \
  --packages-select extra_dof_control \
  --symlink-install

source install/setup.bash
```

Then restart the ActionServer from the RevPi host:

```bash
sudo systemctl restart extra-dof-action-server.service
```

Verify that it is running:

```bash
sudo systemctl status extra-dof-action-server.service --no-pager -l
```

The same principle applies to `MoveAxis.action`: because the generated Action interface is used by both the control PC and the RevPi, interface changes must be rebuilt on both systems.

---

## Building after code changes

### Important: Action definition changes

`MoveAxis.action` is used by both the control PC and the RevPi.

If the Action definition changes, rebuild `extra_dof_control` on **both devices** so that the generated ROS interface matches.

### Action package

Inside the ROS 2 workspace:

```bash
cd ~/ros2_ws
source /opt/ros/humble/setup.bash

colcon build   --packages-select extra_dof_control   --symlink-install

source install/setup.bash
```

On the RevPi, restart the ActionServer afterward:

```bash
sudo systemctl restart extra-dof-action-server.service
```

### Motor controller package

Only rebuild `linear_motor` when the motor-node code or configuration changes.

Inside the RevPi ROS 2 container:

```bash
cd /ros2_ws
source /opt/ros/humble/setup.bash

colcon build   --packages-select linear_motor   --symlink-install

source install/setup.bash
```

Then on the RevPi host:

```bash
sudo systemctl restart linear-motor.service
```

A full Docker container restart is normally unnecessary. Restart the relevant `systemd` service after rebuilding instead.

---

## Basic diagnostics

### RevPi nodes

Inside the RevPi ROS 2 environment:

```bash
ROS2CLI_NO_DAEMON=1 ros2 node list
```

Expected nodes include:

```text
/la11_encoder_node
/revpi_closed_loop_motor_node
/extra_dof/extra_dof_action_server
```

### RevPi topics

```bash
ROS2CLI_NO_DAEMON=1 ros2 topic list | grep -E 'revpi|la11'
```

Expected topics include:

```text
/la11_encoder_node/position_mm
/revpi_closed_loop_motor_node/position_mm
/revpi_closed_loop_motor_node/preset
/revpi_closed_loop_motor_node/target_mm
```

### ActionServer

```bash
ROS2CLI_NO_DAEMON=1 ros2 action info /extra_dof/move_axis
```

Expected:

```text
Action servers: 1
```

### Recent ActionServer logs

```bash
sudo journalctl   -u extra-dof-action-server.service   -n 50   --no-pager
```

### Recent motor-controller logs

```bash
sudo journalctl   -u linear-motor.service   -n 50   --no-pager
```

---

## Closed-loop motor configuration

The motor node is the main configuration location for fixed motor-controller settings such as:

```text
encoder topic
target/preset/position topics
RevPi IO names
PWM duty
enable and direction logic
tolerance
minimum movement threshold
minimum and maximum target positions
overshoot limits
encoder timeout
control period
maximum move duration
preset positions
```

The launch file is intentionally kept minimal and only starts the node.

Current important values include:

```text
min_target_mm = 46.0
max_target_mm = 290.0

preset_0 = 59.0
preset_1 = 168.0
preset_2 = 277.0
```

After changing these values, rebuild `linear_motor` and restart `linear-motor.service`.

---

## Notes on old commands

Older project notes contained manual commands for:

1. starting the LA11 encoder container/node,
2. starting the RevPi motor controller container/node,
3. manually restarting Docker containers after code changes,
4. sending arbitrary millimetre targets through the Action.

These are no longer part of the normal workflow.

The current intended external interface is:

```text
MoveAxis Action
    +
preset_index = 0, 1 or 2
```

Useful maintenance commands retained from the older notes include:

- ROS domain configuration
- SSH via `RevPi160200.local`
- live encoder/position monitoring
- `colcon build --symlink-install`
- service restart commands
- Action communication checks

---

## Recommended quick verification after changes

On the RevPi:

```bash
sudo systemctl status linear-motor.service --no-pager -l
sudo systemctl status extra-dof-action-server.service --no-pager -l
```

On the control PC:

```bash
export ROS_DOMAIN_ID=42
export ROS_LOCALHOST_ONLY=0

ROS2CLI_NO_DAEMON=1 ros2 action info /extra_dof/move_axis
```

Then test one preset:

```bash
ros2 action send_goal   /extra_dof/move_axis   extra_dof_control/action/MoveAxis   "{preset_index: 1}"   --feedback
```

Finally, test rejection:

```bash
ros2 action send_goal   /extra_dof/move_axis   extra_dof_control/action/MoveAxis   "{preset_index: 3}"   --feedback
```

The first goal should complete normally and the invalid preset should be rejected.