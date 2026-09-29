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

The RevPi motor controller and ActionServer are configured to start automatically through `systemd`. The LA11 encoder node on the Raspberry Pi also starts automatically through `systemd`.

---

## ROS 2 network

The deployed system uses the default ROS 2 domain:

```bash
ROS_DOMAIN_ID=0
```

On the Digitop control PC, `ROS_DOMAIN_ID` may remain unset because ROS 2 defaults to domain 0.

All ROS 2 devices participating in the extra-DOF system must use domain 0.

### RevPi ROS domain configuration

The RevPi runtime startup scripts explicitly set domain 0:

```text
/home/pi/ros2_ws/start_linear_motor.sh
/home/pi/ros2_ws/start_extra_dof_action_server.sh
```

Both scripts contain:

```bash
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
```

After changing ROS or network settings, restart the RevPi services:

```bash
sudo systemctl restart linear-motor.service
sudo systemctl restart extra-dof-action-server.service
```

#### Existing container note

The existing `ros2-linear-motor` Docker container was originally created with `ROS_DOMAIN_ID=42` in its stored Docker environment. The running motor node and ActionServer are nevertheless on domain 0 because their startup scripts explicitly override the container value.

Interactive/login shells inside the container have also been configured to use domain 0. If the container is recreated in the future, it should preferably be created with `ROS_DOMAIN_ID=0` or with `ROS_DOMAIN_ID` unset.

### Raspberry Pi ROS domain configuration

The Raspberry Pi LA11 encoder runs on the default ROS domain 0.

Its startup script inside `my-ros2-container` is:

```text
/ros2_ws/start_la11_encoder.sh
```

The service used to start it is:

```text
la11-encoder.service
```

Check or restart it with:

```bash
sudo systemctl status la11-encoder.service --no-pager
sudo systemctl restart la11-encoder.service
```

---

## Network layout

Current deployment:

```text
Digitop control PC
  enp12s0: 192.169.255.77/24
        |
        | Ethernet switch
        |
RevPi
  physical Port A / Socket A (eth0): 192.169.255.160/24
  physical Port B / Socket B (eth1): 192.168.50.1/24
        |
        | Dedicated RevPi-Raspberry Pi link
        |
Raspberry Pi
  192.168.50.2/24
```

On the RevPi Connect 4 running the current Bookworm-based system, physical **Port/Socket A corresponds to `eth0`** and is the control-PC/switch connection. Physical **Port/Socket B corresponds to `eth1`** and is used for the dedicated Raspberry Pi link.

The Raspberry Pi is connected to the RevPi through the separate `192.168.50.0/24` network and publishes LA11 encoder feedback on:

```text
/la11_encoder_node/position_mm
```

The RevPi receives this feedback and uses it for closed-loop motor control.


### Raspberry Pi LA11 SPI connection

The LA11 encoder node uses Raspberry Pi **SPI bus 0, chip-select 0** (`/dev/spidev0.0`). The corresponding 40-pin header signals are:

| LA11 SPI signal | Raspberry Pi function | BCM GPIO | Physical pin |
|---|---|---:|---:|
| Clock / SCK | SPI0 SCLK | GPIO11 | 23 |
| Data / MISO | SPI0 MISO | GPIO9 | 21 |
| Chip select / CS | SPI0 CE0 | GPIO8 | 24 |
| MOSI | SPI0 MOSI | GPIO10 | 19 |

The LA11 SPI readout uses clock, chip-select and MISO/data. MOSI is part of the Raspberry Pi SPI0 interface but is not required by the LA11 SPI output itself.

A common signal ground is also required. The exact encoder supply wiring is intentionally not specified here because it depends on the installed LA11 electrical/output variant and the existing interface hardware. Raspberry Pi GPIO is **3.3 V logic only**; verify the LA11 signal-level variant before making a direct GPIO connection.

The software-side SPI selection can be confirmed in the encoder node by the equivalent of:

```python
spi.open(0, 0)
```

which selects SPI0 with CE0.

### SSH aliases on the Digitop

A convenient Digitop SSH configuration is:

```text
Host revpi
    HostName 192.169.255.160
    User pi

Host raspberrypi
    HostName 192.168.50.2
    User pi
    ProxyJump revpi
```

This allows:

```bash
ssh revpi
ssh raspberrypi
```

### After changing the RevPi network interface or IP address

If the RevPi IP address is changed or the device is moved to another switch/interface, basic `ping` and SSH may work while ROS 2 discovery still uses information from when the DDS participants were started.

Restart the RevPi ROS services after such a network change:

```bash
sudo systemctl restart linear-motor.service
sudo systemctl restart extra-dof-action-server.service
```

---

## Automatic startup

The following components should start automatically.

### RevPi

```text
linear-motor.service
extra-dof-action-server.service
```

Check their status:

```bash
sudo systemctl status linear-motor.service --no-pager -l
sudo systemctl status extra-dof-action-server.service --no-pager -l
```

### Raspberry Pi

```text
la11-encoder.service
```

Check its status:

```bash
sudo systemctl status la11-encoder.service --no-pager -l
```

Manual Docker/node startup commands are normally **not needed during normal operation**.

---

## Main ROS interfaces

### Action

Action name:

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

The closed-loop motor node contains minimum and maximum target limits for low-level motor safety:

```text
min_target_mm = 46.0
max_target_mm = 290.0
```

These limits are not part of the public Action command interface because the Action accepts presets only.

---

## Quick control-PC setup

On the Digitop control PC, source ROS 2 and the local workspace before using the custom Action interface:

```bash
source /opt/ros/humble/setup.bash
source ~/Desktop/ros_ws/install/setup.bash
```

The workspace overlay is required because it provides the locally built package and generated Action interface:

```text
extra_dof_control/action/MoveAxis
extra_dof_py
```

Without sourcing the workspace, ROS discovery may still show the remote RevPi nodes, but the control PC will not know the custom Action type. A typical CLI symptom is:

```text
The passed action type is invalid
```

Check the relevant nodes:

```bash
ros2 node list --no-daemon --spin-time 3
```

Expected RevPi nodes include:

```text
/extra_dof/extra_dof_action_server
/revpi_closed_loop_motor_node
```

Check the Action and type:

```bash
ros2 action list -t
```

Expected:

```text
/extra_dof/move_axis [extra_dof_control/action/MoveAxis]
```

You can also inspect the Action server with:

```bash
ros2 action info /extra_dof/move_axis
```

---

## Action tests

The command-line tests in this section can be run directly from the **JupyterLab terminal** on the Digitop. JupyterLab should first be started from a shell where ROS 2 and the Digitop workspace overlay have been sourced, as described in the [Jupyter example](#jupyter-example). Terminals opened from that JupyterLab session inherit the same ROS environment.

For notebook-based checks, use the existing **`test_extradof_paket.ipynb`** notebook. It can be used to verify the generated `MoveAxis` interface, import and instantiate `AxisClient`, and send preset goals through `/extra_dof/move_axis`. Restart the notebook kernel before a clean test run so that only one `AxisClient` instance is active.

Only run movement tests when the extra axis is clear and safe to move.

### Preset 0

```bash
ros2 action send_goal \
  /extra_dof/move_axis \
  extra_dof_control/action/MoveAxis \
  "{preset_index: 0}" \
  --feedback
```

### Preset 1

```bash
ros2 action send_goal \
  /extra_dof/move_axis \
  extra_dof_control/action/MoveAxis \
  "{preset_index: 1}" \
  --feedback
```

### Preset 2

```bash
ros2 action send_goal \
  /extra_dof/move_axis \
  extra_dof_control/action/MoveAxis \
  "{preset_index: 2}" \
  --feedback
```

### Invalid preset rejection test

```bash
ros2 action send_goal \
  /extra_dof/move_axis \
  extra_dof_control/action/MoveAxis \
  "{preset_index: 3}" \
  --feedback
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
ros2 topic echo \
  /revpi_closed_loop_motor_node/position_mm \
  --qos-reliability best_effort
```

The raw LA11 encoder topic is:

```text
/la11_encoder_node/position_mm
```

The Raspberry Pi is on a separate network behind the RevPi, so the raw encoder topic may not always be directly discoverable from the control PC. It should be visible from the RevPi on ROS domain 0.

To test it from the RevPi container:

```bash
docker exec ros2-linear-motor bash -lc '
source /opt/ros/humble/setup.bash
source /ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
ros2 topic echo /la11_encoder_node/position_mm --once
'
```

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

### Jupyter example

The existing **`test_extradof_paket.ipynb`** notebook is the preferred quick test notebook for the extra-DOF package. It can be used for import checks, `AxisClient` creation, and preset goal tests. Command-line diagnostics and `ros2 action send_goal` tests can be run from the terminal built into the same JupyterLab session.

Jupyter must be started from a shell in which ROS 2 and the workspace overlay have already been sourced.

On the Digitop:

```bash
cd ~/Desktop/ros_ws/src
source .venv/bin/activate
source /opt/ros/humble/setup.bash
source ~/Desktop/ros_ws/install/setup.bash
jupyter-lab --allow-root
```

Then in the notebook:

```python
import rclpy
from extra_dof_control.action import MoveAxis
from extra_dof_py.axis_client import AxisClient

if not rclpy.ok():
    rclpy.init()

axis = AxisClient()
```

Example move:

```python
success = axis.send_goal(1)
print("Action result:", success)
```

Avoid creating multiple `AxisClient` instances in the same notebook session unless required, because they currently use the same ROS node name. If duplicate `/extra_dof_action_client` nodes appear, restart the notebook kernel and create the client once.

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

Inside a ROS 2 workspace:

```bash
cd ~/ros2_ws
source /opt/ros/humble/setup.bash

colcon build \
  --packages-select extra_dof_control \
  --symlink-install

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

colcon build \
  --packages-select linear_motor \
  --symlink-install

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
ros2 node list --no-daemon --spin-time 3
```

Expected nodes include:

```text
/la11_encoder_node
/revpi_closed_loop_motor_node
/extra_dof/extra_dof_action_server
```

### RevPi topics

```bash
ros2 topic list | grep -E 'revpi|la11'
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
ros2 action info /extra_dof/move_axis
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

### Raspberry Pi encoder logs

```bash
sudo journalctl \
  -u la11-encoder.service \
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

Older project notes contained manual commands for:

1. starting the LA11 encoder container/node,
2. starting the RevPi motor controller container/node,
3. manually restarting Docker containers after code changes,
4. sending arbitrary millimetre targets through the Action,
5. using ROS domain 42.

These are no longer part of the normal workflow.

The current intended external interface is:

```text
MoveAxis Action
    +
preset_index = 0, 1 or 2
```

The current deployed ROS domain is 0.

Useful maintenance commands retained from the older notes include:

- SSH access to the RevPi and Raspberry Pi
- live encoder/position monitoring
- `colcon build --symlink-install`
- service restart commands
- Action communication checks

---

## Recommended quick verification after changes

### 1. Check RevPi services

```bash
sudo systemctl status linear-motor.service --no-pager -l
sudo systemctl status extra-dof-action-server.service --no-pager -l
```

### 2. Check the Raspberry Pi encoder service if encoder feedback is missing

```bash
sudo systemctl status la11-encoder.service --no-pager -l
```

### 3. On the Digitop, source the workspace

```bash
source /opt/ros/humble/setup.bash
source ~/Desktop/ros_ws/install/setup.bash
```

### 4. Check ROS discovery

```bash
ros2 node list --no-daemon --spin-time 3
ros2 action list -t
```

Expected RevPi nodes:

```text
/extra_dof/extra_dof_action_server
/revpi_closed_loop_motor_node
```

Expected Action:

```text
/extra_dof/move_axis [extra_dof_control/action/MoveAxis]
```

### 5. Test one preset

```bash
ros2 action send_goal \
  /extra_dof/move_axis \
  extra_dof_control/action/MoveAxis \
  "{preset_index: 1}" \
  --feedback
```

### 6. Test invalid-preset rejection

```bash
ros2 action send_goal \
  /extra_dof/move_axis \
  extra_dof_control/action/MoveAxis \
  "{preset_index: 3}" \
  --feedback
```

The first goal should complete normally and the invalid preset should be rejected.