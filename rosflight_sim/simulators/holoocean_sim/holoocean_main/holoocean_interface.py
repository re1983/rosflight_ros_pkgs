import numpy as np
from pathlib import Path
import holoocean
import json
import subprocess


class HolooceanInterface():
    """
    Lightweight wrapper around holoocean for loading a scenario file and advancing the simulation,
    returning sensor data.
    """
    def __init__(
        self,
        scenario_path,
        tps=30,
        show_viewport=True,
        render_quality=None,
        disable_screen_messages=False,
    ):
        """
        Parameters:
            scenario_path (str or Path): Path to the scenario file
            tps (int): ticks per second for the simulation
            show_viewport (bool): Whether to show the simulation viewport
            render_quality (int or None): Render quality setting for the simulation
            disable_screen_messages (bool): Whether to ask Unreal to hide on-screen messages
        
        Attributes:
            env: The holoocean environment instance
            agent: The main agent in the scenario
            sensors: The sensors attached to the main agent
        """
        self.tps = tps
        scenario_path = Path(scenario_path)     # Ensure a Path object for the scenario path.

        # Load scenario file.
        with open(str(scenario_path), 'r') as f:
            scenario = json.load(f)

        # Define necessary sensors for detecting collisions.
        collision_sensors = [
            {
            "sensor_name": "GroundRange",
            "sensor_type": "RangeFinderSensor",
            "socket": "COM",
            "configuration": {
                "LaserMaxDistance": 100.0,
                "LaserCount": 1,
                "LaserAngle": -90.0,
                "LaserDebug": False
            }
            },
            {
            "sensor_name": "HorizontalRange",
            "sensor_type": "RangeFinderSensor",
            "socket": "COM",
            "configuration": {
                "LaserMaxDistance": 50.0,
                "LaserCount": 6,
                "LaserAngle": 0.0,
                "LaserDebug": False
            }
            }
        ]

        # Append sensors to main agent's sensor list.
        scenario["agents"][0]["sensors"].extend(collision_sensors)

        # Create environment using ticks_per_sec parameter.
        self.env = self._make_environment(
            scenario,
            show_viewport=show_viewport,
            disable_screen_messages=disable_screen_messages,
        )
        self.agent = self.env.agents[scenario["main_agent"]]
        self.sensors = self.agent.sensors
        self.ros_publish = scenario["ros_publish"]

        # Initial step to populate state.
        command = np.zeros(6) if 'fixedwing' in str(scenario_path) else np.zeros(4)
        self.state = self.env.step(command)
        self.render_quality = render_quality

    def _make_environment(self, scenario, show_viewport=True, disable_screen_messages=False):
        if not disable_screen_messages:
            return holoocean.make(
                scenario_cfg=scenario,
                show_viewport=show_viewport,
                ticks_per_sec=self.tps,
            )

        original_popen = subprocess.Popen

        def patched_popen(*popen_args, **popen_kwargs):
            args = popen_args[0] if popen_args else popen_kwargs.get("args")
            if isinstance(args, list) and "-HolodeckOn" in args:
                if "-ExecCmds=DisableAllScreenMessages" not in args:
                    args = [*args, "-ExecCmds=DisableAllScreenMessages"]
                    if popen_args:
                        popen_args = (args,) + popen_args[1:]
                    else:
                        popen_kwargs["args"] = args
            return original_popen(*popen_args, **popen_kwargs)

        subprocess.Popen = patched_popen
        try:
            return holoocean.make(
                scenario_cfg=scenario,
                show_viewport=show_viewport,
                ticks_per_sec=self.tps,
            )
        finally:
            subprocess.Popen = original_popen

    def set_render_quality(self, value=None):
        """
        Set the render quality of the environment.
        value (int or None): Render quality setting. If None, uses the existing setting.
        """
        if value is not None:
            self.render_quality = value
        if self.render_quality is not None:
            self.env.set_render_quality(self.render_quality)

    def set_agent_state(self, location, rotation, velocity, angular_velocity):
        """
        Update an agent's physics state in the simulation (does not advance sim).
        Parameters:
            location (ndarray): New position of the agent
            rotation (ndarray): New orientation of the agent (e.g., Euler angles or quaternion)
            velocity (ndarray): New linear velocity of the agent
            angular_velocity (ndarray): New angular velocity of the agent
        """
        self.agent.set_physics_state(location, rotation, velocity, angular_velocity)
    
    def tick(self):
        """
        Progresses the simulation by one tick and update sensor data.
        Returns:
            sensors_data (dict): dictionary mapping agents to latest sensor data
        """
        sensors_data = self.env.tick()
        return sensors_data
    
    def sensor_callback(self, sensor_name):
        """
        Get latest sensor data from the simulation
        Parameters:
            sensor_name (str): Name of the sensor to retrieve data from
        Returns:
            sensor_data: The latest data from the specified sensor
        """
        sensor_data = self.sensors[sensor_name].sensor_data
        return sensor_data

    def reset_environment(self):
        """
        Reset the environment and repopulate state
        """
        self.state = self.env.reset()
        self.set_render_quality()
