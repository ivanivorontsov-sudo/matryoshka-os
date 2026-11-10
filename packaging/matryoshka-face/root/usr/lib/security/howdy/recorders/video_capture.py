# Top level class for a video capture providing simplified API's for common
# functions

# Import required modules
import configparser
import cv2
import os
import sys
import time


def _sysfs_name(dev):
	try:
		with open("/sys/class/video4linux/" + os.path.basename(dev) + "/name") as f:
			return f.read().strip()
	except Exception:
		return ""


def _sysfs_index(dev):
	try:
		with open("/sys/class/video4linux/" + os.path.basename(dev) + "/index") as f:
			return int(f.read().strip())
	except Exception:
		return 0


def find_camera(path):
	if path and path != "none" and os.path.exists(path):
		return os.path.realpath(path)
	try:
		with open("/etc/matryoshka/face-device") as f:
			saved = f.read().strip()
		if saved and os.path.exists(saved):
			return os.path.realpath(saved)
	except Exception:
		pass
	devs = []
	try:
		devs = sorted("/dev/" + d for d in os.listdir("/sys/class/video4linux") if d.startswith("video"))
	except Exception:
		pass
	devs = [d for d in devs if os.path.exists(d) and _sysfs_index(d) == 0]
	ir = [d for d in devs if " ir" in (" " + _sysfs_name(d).lower().replace("-", " ").replace("_", " ")) or "infrared" in _sysfs_name(d).lower()]
	if ir:
		return ir[0]
	if len(devs) == 1:
		return devs[0]
	return None


# Class to provide boilerplate code to build a video recorder with the
# correct settings from the config file.
#
# The internal recorder can be accessed with 'video_capture.internal'


class VideoCapture:
	def __init__(self, config):
		"""
		Creates a new VideoCapture instance depending on the settings in the
		provided config file.

		Config can either be a string to the path, or a pre-setup configparser.
		"""

		# Parse config from string if nedded
		if isinstance(config, str):
			self.config = configparser.ConfigParser()
			self.config.read(config)
		else:
			self.config = config

		self.internal = None
		self.device = find_camera(self.config.get("video", "device_path", fallback="none"))
		if not self.device:
			print("Camera path is not configured correctly, please edit the 'device_path' config value.")
			sys.exit(1)

		# Create reader
		# The internal video recorder
		self.internal = None
		# The frame width
		self.fw = None
		# The frame height
		self.fh = None
		for attempt in range(8):
			self._create_reader()
			if not hasattr(self.internal, "isOpened") or self.internal.isOpened():
				break
			self.release()
			time.sleep(0.4)
		if self.internal is None:
			print("Camera is busy or unavailable: " + self.device)
			sys.exit(1)

		# Request a frame to wake the camera up
		self.internal.grab()

	def __del__(self):
		"""
		Frees resources when destroyed
		"""
		self.release()

	def release(self):
		"""
		Release cameras
		"""
		internal = getattr(self, "internal", None)
		if internal is not None:
			try:
				internal.release()
			except Exception:
				pass
			self.internal = None

	def read_frame(self):
		"""
		Reads a frame, returns the frame and an attempted grayscale conversion of
		the frame in a tuple:

		(frame, grayscale_frame)

		If the grayscale conversion fails, both items in the tuple are identical.
		"""

		# Grab a single frame of video
		# Don't remove ret, it doesn't work without it
		ret, frame = self.internal.read()
		if not ret:
			print("Failed to read camera specified in your 'device_path', aborting")
			sys.exit(1)

		try:
			# Convert from color to grayscale
			# First processing of frame, so frame errors show up here
			gsframe = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
		except RuntimeError:
			gsframe = frame
		except cv2.error:
			print("\nAn error occurred in OpenCV\n")
			raise
		return frame, gsframe

	def _create_reader(self):
		"""
		Sets up the video reader instance
		"""

		if self.config.get("video", "recording_plugin") == "ffmpeg":
			# Set the capture source for ffmpeg
			from recorders.ffmpeg_reader import ffmpeg_reader
			self.internal = ffmpeg_reader(
				self.device,
				self.config.get("video", "device_format")
			)

		elif self.config.get("video", "recording_plugin") == "pyv4l2":
			# Set the capture source for pyv4l2
			from recorders.pyv4l2_reader import pyv4l2_reader
			self.internal = pyv4l2_reader(
				self.device,
				self.config.get("video", "device_format")
			)

		else:
			# Start video capture on the IR camera through OpenCV
			self.internal = cv2.VideoCapture(self.device, cv2.CAP_V4L2)

		# Force MJPEG decoding if true
		if self.config.getboolean("video", "force_mjpeg", fallback=False):
			# Set a magic number, will enable MJPEG but is badly documentated
			self.internal.set(cv2.CAP_PROP_FOURCC, 1196444237)

		# Set the frame width and height if requested
		self.fw = self.config.getint("video", "frame_width", fallback=-1)
		self.fh = self.config.getint("video", "frame_height", fallback=-1)
		if self.fw != -1:
			self.internal.set(cv2.CAP_PROP_FRAME_WIDTH, self.fw)
		if self.fh != -1:
			self.internal.set(cv2.CAP_PROP_FRAME_HEIGHT, self.fh)
