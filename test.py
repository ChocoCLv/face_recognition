# coding=utf-8
from multiprocessing import Process, Queue, Manager
import face_recognition
import cv2
import socket
import os
import time
import json
import sys
import threading
import configparser
from plc_control_msg import door_ctl_msg

# 运行参数  从配置文件传入config.ini
config = {}

# 识别结果的消息封装
msg = {}


def nowTime(): return int(round(time.time() * 1000))

# 更新人脸标准库


def load_encode_image():
    # 遍历./faces文件夹下的所有文件夹，即对应不同人员id的照片信息，子文件夹名即为人员id
    # 例如 文件夹./faces/1里存储了id为1的人员的照片
    known_face_encodings = {}
    dir_list = os.listdir(config['SAMPLE_DIR'])
    for i in range(0, len(dir_list)):
        path = os.path.join(config['SAMPLE_DIR'], dir_list[i])
        if os.path.isdir(path):

            known_face_encodings[dir_list[i]] = []
            image_list = os.listdir(path)

            for j in range(0, len(image_list)):
                image_path = os.path.join(path, image_list[j])
                print('[LOAD_ENCODE_IMAGE]: ' + config['CAMERA_NAME'] + '-' +
                      image_path)
                image = face_recognition.load_image_file(image_path)
                try:
                    start_time = nowTime()
                    image_encoding = face_recognition.face_encodings(image)[0]
                    end_time = nowTime()
                    print("encoding time: "+str(end_time - start_time))
                    known_face_encodings[dir_list[i]].append(image_encoding)
                except:
                    print('encode error')
                    pass

    return known_face_encodings


# 监听进程 用于处理客户端的连接请求
def serverProcessFunc(push_socks1, push_socks2, push_socks3):
    print('[PROCESS]: server process start')
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('127.0.0.1', config['LISTEN_PORT']))
    server.listen(10)
    while True:
        conn, addr = server.accept()
        # 客户端连接上都会马上发一条指令
        bytes_data = conn.recv(100)
        if bytes_data:
            str_data = str(bytes_data)
            if str_data.find('134') != -1:
                print('[SERVER]: get update command')
                conn.close()
            elif str_data.find('130') != -1:
                print('[SERVER]:get new push sock')
                print(str_data)
                command = str_data.split(':')
                command_msg = command[2].split(',')
                camera_name = command_msg[2]
                if camera_name == 'camera1':
                    push_socks1.put(conn)
                elif camera_name == 'camera2':
                    push_socks2.put(conn)
                elif camera_name == 'camera3':
                    push_socks3.put(conn)


# PLC通信进程 在需要开门时会启动该进程
# 正常开门或者超时后还未检测到刷卡信号结束进程
def plcProcessFunc():
    seconds = 0
    door = -1
    plc_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    plc_sock.connect((config['PLC_HOST'], config['PLC_PORT']))
    # print(config['CAMERA_NAME']+'-'+config['PLC_HOST'])
    while seconds <= config['PLC_TIME_OUT']:
        plc_sock.send(door_ctl_msg['check'])
        door_status = plc_sock.recv(1024)
        # print(door_status)
        # check which door should be opened
        if door_status[3] == 0x01:
            door = 1
            break
        elif door_status[3] == 0x02:
            door = 2
            break
        elif door_status[3] == 0x04:
            door = 3
            break
        elif door_status[3] == 0x10:
            door = 4
            break
        elif door_status[3] == 0x00:
            print('all closed')
        seconds = seconds + 0.2
        time.sleep(1)

    if door == -1:
        plc_sock.close()
        return
    print(config['CAMERA_NAME']+'[OPEN_DOOR]: open door: No.' + str(door))
    plc_sock.send(door_ctl_msg[door]['open'])
    time.sleep(config['PLC_CLOSE_DELAY_TIME'])
    plc_sock.send(door_ctl_msg[door]['close'])
    plc_sock.close()


# 启动PLC通信进程
def openDoor():
    plcProcess = Process(target=plcProcessFunc)
    plcProcess.start()


# 识别结果推送进程
# 监听进程收到需要推送结果的连接后存入套接字队列
# 摄像头进程检测到人脸后也会将识别结果存入消息队列
# 该进程会不断从消息队列中取出消息 然后向每个套接字推送
def pushProcessFunc(push_socks1, push_socks2, push_socks3, msg_queue):
    while True:
        msg = msg_queue.get(True)
        time.sleep(1)
        camera_name = msg['captureName']
        socks = push_socks1
        if camera_name == 'camera1':
            socks = push_socks1
        elif camera_name == 'camera2':
            socks = push_socks1
        elif camera_name == 'camera3':
            socks = push_socks1
        socks_num = socks.qsize()
        while socks_num > 0:
            sock = socks.get(True)
            socks_num = socks_num-1
            try:
                msg_json = json.dumps(msg)
                bs = bytes(msg_json + '\n', encoding="utf8")
                sock.send(bs)
                socks.put(sock)
            except:
                sock.close()


# 识别到同一个人并且定时器未启动时即启动定时器
# 定时器超时后会修改last_recog_id 即可以再次为同一个人开门
timer_is_run = False

# 定时器超时函数


def timerFunc():
    global timer_is_run
    time.sleep(config['FACE_DETECT_DELAY_TIME'])
    timer_is_run = False

# 人脸识别进程
# 对应不同的摄像头
# 目前只在启动时对人脸库进行编码  web端未作更新指令


def run(msg_queue):
    process_this_frame = 0
    # known_face_encodings = load_encode_image()
    global timer_is_run
    msg['captureName'] = config['CAMERA_NAME']
    # 大华摄像头
    camera_url = 'rtsp://{username}:{password}@{ip}/cam/realmonitor?channel=1&subtype=0'.format(
        username=config['CAMERA_USERNAME'],
        password=config['CAMERA_PASSWORD'],
        ip=config['CAMERA_IP'])
    video_capture = cv2.VideoCapture(camera_url)

    while True:
        # Grab a single frame of video
        round_start_time = nowTime()
        ret, frame = video_capture.read()
        if not ret:
            print('未读到有效帧数据')
            continue

        # 滤波

        # Resize frame of video to 1/4 size for faster face recognition processing
        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)

        # Convert the image from BGR color (which OpenCV uses) to RGB color (which face_recognition uses
        rgb_small_frame = small_frame[:, :, ::-1]

        # Only process every other frame of video to save time
        process_this_frame = (process_this_frame + 1) % 2

        if process_this_frame == 0:
            # Find all the faces and face encodings in the current frame of video
            start_time = nowTime()
            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_num = len(face_locations)
            print('face num: '+str(face_num))
            end_time = nowTime()
            print('location time: '+str(end_time - start_time))

            # start_time = nowTime()
            # face_encodings = face_recognition.face_encodings(
            #     rgb_small_frame, face_locations)
            # end_time = nowTime()
            # print('encoding time: '+str(end_time - start_time))

            # if face_num != 0:
            #     allow_pass = False

            #     msg['faceNumber'] = face_num
            #     msg['data'] = []

            #     total_min_distance = 1
            #     min_id = -1

            #     # 判断识别图片中的人脸id
            #     for face_encoding in face_encodings:
            #         # See if the face is a match for the known face(s)
            #         for face_id in known_face_encodings:
            #             distances = list(
            #                 face_recognition.face_distance(
            #                     known_face_encodings[face_id], face_encoding))

            #             min_distance = min(distances)
            #             # 存储距离最近的人脸id 在识别失败的时候使用
            #             if total_min_distance > min_distance:
            #                 total_min_distance = min_distance
            #                 min_id = face_id

            #             if min_distance <= config['FACE_DISTANCE']:
            #                 face = {}
            #                 face['id'] = face_id
            #                 face['compare'] = 1 - min_distance
            #                 msg['data'].append(face)
            #                 allow_pass = True
            #                 break

            #     # 控制plc开门
            #     file_name = ''
            #     if allow_pass:
            #         file_name = 'ok_' + config['CAMERA_NAME'] + '_' + str(
            #             end_time) + '.jpg'
            #         msg['type'] = 0
            #         print('[CAMERA]: ' + config['CAMERA_NAME'] + '-' + '合法')

            #     else:
            #         file_name = 'warn_' + config['CAMERA_NAME'] + '_' + str(
            #             end_time) + '.jpg'
            #         msg['type'] = 1
            #         face = {}
            #         face['id'] = min_id
            #         face['compare'] = 1 - total_min_distance
            #         msg['data'].append(face)
            #         print('[CAMERA]: ' + config['CAMERA_NAME'] + '-' + '非法')

            #     # 将人脸图片保存  并将路径填入msg中

            #     msg['filePath'] = file_path

            #     # 向web端发送识别结果
            #     msg['cmd'] = 130
            #     msg['ack'] = 123456
            #     msg_queue.put(msg)
            round_end_time = nowTime()
            print('round time: '+str(round_end_time - round_start_time))

            for (top, right, bottom, left) in face_locations:
                # Scale back up face locations since the frame we detected in was scaled to 1/4 size
                top *= 4
                right *= 4
                bottom *= 4
                left *= 4

                # Draw a box around the face
                cv2.rectangle(frame, (left, top),
                              (right, bottom), (0, 0, 255), 2)

            file_name = 'test_' + config['CAMERA_NAME'] + '_' + str(
                end_time) + '.jpg'
            file_path = config['PICTURE_SAVE_DIR'] + os.path.sep + file_name
            cv2.imwrite(file_path, frame)

        # 显示实时画面  测试用
        cv2.imshow('Video', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    video_capture.release()
    video_writer.release()


manager = Manager()

if __name__ == '__main__':
    # 添加进程间共享变量
    push_socks1 = Queue()
    push_socks2 = Queue()
    push_socks3 = Queue()

    msg_queue = Queue()
    cf = configparser.ConfigParser()
    cf.read('./config.ini')
    config['LISTEN_PORT'] = cf.getint('base', 'LISTEN_PORT')
    config['SAMPLE_DIR'] = cf.get('base', 'SAMPLE_DIR')
    config['PICTURE_SAVE_DIR'] = cf.get('base', 'PICTURE_SAVE_DIR')
    config['FACE_DETECT_DELAY_TIME'] = cf.getint(
        'base', 'FACE_DETECT_DELAY_TIME')
    config['PLC_TIME_OUT'] = cf.getint('base', 'PLC_TIME_OUT')
    config['FACE_DISTANCE'] = cf.getfloat('base', 'FACE_DISTANCE')
    config['PLC_CLOSE_DELAY_TIME'] = cf.getint('base', 'PLC_CLOSE_DELAY_TIME')

    try:
        for camera in cf.sections():
            if camera.find('camera') == -1:
                continue
            config['CAMERA_NAME'] = cf.get(camera, 'CAMERA_NAME')
            config['CAMERA_IP'] = cf.get(camera, 'CAMERA_IP')
            config['CAMERA_USERNAME'] = cf.get(camera, 'CAMERA_USERNAME')
            config['CAMERA_PASSWORD'] = cf.get(camera, 'CAMERA_PASSWORD')
            config['PLC_HOST'] = cf.get(camera, 'PLC_HOST')
            config['PLC_PORT'] = cf.getint(camera, 'PLC_PORT')
            cameraProcess = Process(
                target=run, name=config['CAMERA_NAME'], args=(msg_queue, ))
            print('create %s process complete' % config['CAMERA_NAME'])
            cameraProcess.start()

    except:
        print('quit')
        cv2.destroyAllWindows()
