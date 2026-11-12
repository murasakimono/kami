import time, logging, sys
logging.basicConfig(level=logging.INFO)
sys.path.insert(0, ".")
from app.core.recorder import Recorder
from app.engines.ytdlp_engine import find_ffmpeg
S = {"rec_fps": 60, "rec_mic": True, "rec_replay_seconds": 5, "rec_replay_enabled": True}
r = Recorder(find_ffmpeg, S, None)
print("replay", r.start_replay(), r.mode, "sys", r.sys.alive, r.sys.error, "mic", r.mic.alive, r.mic.error)
time.sleep(9)
t = time.time(); print("clip", r.save_replay(5), round(time.time() - t, 2))
print(r.start_record()); time.sleep(4); print(r.stop_record())
r.shutdown()
