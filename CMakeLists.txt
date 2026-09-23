cmake_minimum_required(VERSION 3.8)
project(extra_dof_control)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclpy REQUIRED)
find_package(std_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "action/MoveAxis.action"
)

ament_python_install_package(extra_dof_py)

install(PROGRAMS
  extra_dof_py/axis_server.py
  extra_dof_py/axis_client.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()