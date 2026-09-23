# extra_dof_control

ROS 2 Humble control interface for an additional linear degree of freedom driven by a RevPi-based motor controller.

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

Because of this, the old manual commands for starting the Docker containers and ROS nodes are generally **not needed during normal operation**.

The previous manual startup commands are therefore intentionally omitted from this README.

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
float64 target_mm
---
bool success
float64 final_position_mm
string message
---
float64 current_position_mm
float64 error_mm
```

### Motor node topics

```text
/revpi_closed_loop_motor_node/target_mm
/revpi_closed_loop_motor_node/position_mm
/revpi_closed_loop_motor_node/preset
```

For normal external control, use the **Action interface** rather than publishing directly to the target or preset topics.

---

## Action target convention

The ActionServer supports both preset indices and direct positions using the existing `target_mm` field.

### Presets

```text
0 -> preset_0
1 -> preset_1
2 -> preset_2
```

The actual preset positions are stored in the closed-loop motor node.

Current defaults:

```text
preset_0 = 59.0 mm
preset_1 = 168.0 mm
preset_2 = 277.0 mm
```

### Direct targets

Values in the allowed physical range are interpreted directly as millimetres.

Current ActionServer limits:

```text
minimum = 46.0 mm
maximum = 290.0 mm
```

Therefore:

```text
0, 1, 2       -> preset indices
46 ... 290    -> direct position in mm
anything else -> rejected
```

For example, `2.5` is **not** a preset. It is interpreted as `2.5 mm` and rejected because it is below the allowed range.

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
ros2 action send_goal \
  /extra_dof/move_axis \
  extra_dof_control/action/MoveAxis \
  "{target_mm: 0}" \
  --feedback
```

### Preset 1

```bash
ros2 action send_goal \
  /extra_dof/move_axis \
  extra_dof_control/action/MoveAxis \
  "{target_mm: 1}" \
  --feedback
```

### Preset 2

```bash
ros2 action send_goal \
  /extra_dof/move_axis \
  extra_dof_control/action/MoveAxis \
  "{target_mm: 2}" \
  --feedback
```

The ROS CLI automatically converts these integer literals to the `float64` `target_mm` field.

### Direct position

Example:

```bash
ros2 action send_goal \
  /extra_dof/move_axis \
  extra_dof_control/action/MoveAxis \
  "{target_mm: 175.0}" \
  --feedback
```

### Out-of-range rejection test

```bash
ros2 action send_goal \
  /extra_dof/move_axis \
  extra_dof_control/action/MoveAxis \
  "{target_mm: 400}" \
  --feedback
```

The goal should be rejected and the motor should not move.

---

## Live position monitoring

The closed-loop motor node republishes encoder position on:

```text
/revpi_closed_loop_motor_node/position_mm
```

From the control PC or RevPi:

```bash
ROS2CLI_NO_DAEMON=1 ros2 topic echo \
  /revpi_closed_loop_motor_node/position_mm \
  --qos-reliability best_effort
```

This is the preferred position topic to monitor from the control PC.

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
client.send_goal(168.0)
```

The ActionClient sends commands to:

```text
/extra_dof/move_axis
```

The ActionServer runs on the RevPi.

---

## Building after code changes

### Motor controller package

Inside the RevPi ROS 2 container:

```bash
cd /ros2_ws
source /opt/ros/humble/setup.bash

colcon build \
  --packages-select linear_motor \
  --symlink-install

source install/setup.bash
```

Then on the RevPi host:

```bash
sudo systemctl restart linear-motor.service
```

### Action package

Inside the RevPi ROS 2 container:

```bash
cd /ros2_ws
source /opt/ros/humble/setup.bash

colcon build \
  --packages-select extra_dof_control \
  --symlink-install

source install/setup.bash
```

Then on the RevPi host:

```bash
sudo systemctl restart extra-dof-action-server.service
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
```

The ActionServer node may appear under the configured namespace.

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
sudo journalctl \
  -u extra-dof-action-server.service \
  -n 50 \
  --no-pager
```

### Recent motor-controller logs

```bash
sudo journalctl \
  -u linear-motor.service \
  -n 50 \
  --no-pager
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

The older command reference contained manual commands for:

1. starting the LA11 encoder container/node,
2. starting the RevPi motor controller container/node,
3. manually restarting Docker containers after code changes.

These are no longer part of the normal workflow because the relevant processes are managed by `systemd`.

The useful parts retained from the older notes are:

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

On the PC:

```bash
export ROS_DOMAIN_ID=42
export ROS_LOCALHOST_ONLY=0

ROS2CLI_NO_DAEMON=1 ros2 action info /extra_dof/move_axis
```

Then test one preset:

```bash
ros2 action send_goal \
  /extra_dof/move_axis \
  extra_dof_control/action/MoveAxis \
  "{target_mm: 1}" \
  --feedback
```

and one direct position:

```bash
ros2 action send_goal \
  /extra_dof/move_axis \
  extra_dof_control/action/MoveAxis \
  "{target_mm: 175.0}" \
  --feedback
```
