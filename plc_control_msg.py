# 控制报文定义
door_ctl_msg = {}
# door No.1 control message
door_ctl_msg[1] = {}
door_ctl_msg[1]['open'] = b"\x01\x05\x00\x10\xff\x00\x8d\xff"
door_ctl_msg[1]['close'] = b"\x01\x05\x00\x10\x00\x00\xcc\x0f"
# door No.2 control message
door_ctl_msg[2] = {}
door_ctl_msg[2]['open'] = b"\x01\x05\x00\x11\xff\x00\xdc\x3f"
door_ctl_msg[2]['close'] = b"\x01\x05\x00\x11\x00\x00\x9d\xcf"
# door No.3 control message
door_ctl_msg[3] = {}
door_ctl_msg[3]['open'] = b"\x01\x05\x00\x12\x00\x00\x6d\xcf"
door_ctl_msg[3]['close'] = b"\x01\x05\x00\x12\xff\x00\x2c\x3f"
# door No.4 control message
door_ctl_msg[4] = {}
door_ctl_msg[4]['open'] = b"\x01\x05\x00\x13\xff\x00\x7d\xff"
door_ctl_msg[4]['close'] = b"\x01\x05\x00\x13\x00\x00\x3c\x0f"
door_ctl_msg['check'] = b'\x01\x01\x00\x00\x00\x04\x3D\xC9'