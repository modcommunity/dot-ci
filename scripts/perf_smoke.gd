extends SceneTree
## Headless perf probe: loads a scene, runs it for N seconds, prints one JSON line.
## Usage: godot --headless --path <project> --script <this file> -- <res://scene.tscn> [seconds]

var _scene_path := ""
var _seconds := 5.0
var _started := 0
var _frames := 0
var _work_ms := 0.0
var _load_ms := 0.0
var _stage := 0


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		printerr("perf_smoke: scene path missing")
		quit(2)
		return
	_scene_path = args[0]
	if args.size() > 1:
		_seconds = float(args[1])
	var t0 := Time.get_ticks_usec()
	var packed: Resource = load(_scene_path)
	if not packed is PackedScene:
		printerr("perf_smoke: cannot load %s" % _scene_path)
		quit(2)
		return
	root.add_child((packed as PackedScene).instantiate())
	_load_ms = (Time.get_ticks_usec() - t0) / 1000.0
	_started = Time.get_ticks_msec()


func _process(_delta: float) -> bool:
	if _stage == 0:
		_stage = 1
		return false
	_frames += 1
	_work_ms += Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0
	if Time.get_ticks_msec() - _started < int(_seconds * 1000.0):
		return false
	var out := {
		"scene": _scene_path,
		"load_ms": snappedf(_load_ms, 0.1),
		"frame_ms": snappedf(_work_ms / maxf(_frames, 1), 0.001),
		"nodes": int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)),
		"mem_mb": snappedf(Performance.get_monitor(Performance.MEMORY_STATIC) / 1048576.0, 0.1),
		"frames": _frames,
	}
	print("PERF_SMOKE ", JSON.stringify(out))
	quit(0)
	return true
