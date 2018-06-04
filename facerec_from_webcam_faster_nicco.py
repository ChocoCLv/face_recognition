import face_recognition
import cv2
import socket
import os
import time
import datetime
import json
import threading
import pprint, pickle

CAMERA_NAME = "camera1"
LOCAL_HOST = '127.0.0.1'
UPDATE_PORT = 6666
PUSH_PORT = 7777
SAMPLE_DIR = "./faces"
PICTURE_SAVE_DIR = "/tmp"
FILE_NAME = 'image_encode'
ENCODING_FILE_PATH = os.path.join(SAMPLE_DIR,
                                  FILE_NAME + '.pkl')  # file store encode
# 大华摄像头
video_capture = cv2.VideoCapture(
    'rtsp://admin:admin123@192.168.1.108/cam/realmonitor?channel=1&subtype=0')
plc_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

msg = {}
msg['camera_name'] = CAMERA_NAME

needUpdate = not os.path.exists(ENCODING_FILE_PATH)


# 更新人脸标准库
def load_encode_image():
    # 遍历./faces文件夹下的所有文件夹，即对应不同人员id的照片信息，子文件夹名即为人员id
    # 例如 文件夹./faces/1里存储了id为1的人员的照片
    known_face_encodings = {}
    dir_list = os.listdir(SAMPLE_DIR)
    for i in range(0, len(dir_list)):
        path = os.path.join(SAMPLE_DIR, dir_list[i])
        if os.path.isdir(path):

            known_face_encodings[dir_list[i]] = []
            image_list = os.listdir(path)

            for j in range(0, len(image_list)):
                image_path = os.path.join(path, image_list[j])
                print('Encoding image: ' + image_path)
                image = face_recognition.load_image_file(image_path)
                image_encoding = face_recognition.face_encodings(image)[0]
                known_face_encodings[dir_list[i]].append(image_encoding)

    return known_face_encodings


# Encode and store encode file
def encode_store_file():

    # if image_encode is exsit ,just encode new image
    encodings_his = {}
    if os.path.exists(ENCODING_FILE_PATH):
        pkl_file = open(ENCODING_FILE_PATH, 'rb')

        encodings_his = pickle.load(pkl_file)

        pkl_file.close()

    # 遍历./faces文件夹下的所有文件夹，即对应不同人员id的照片信息，子文件夹名即为人员id
    # 例如 文件夹./faces/1里存储了id为1的人员的照片
    known_face_encodings = encodings_his  # {'chenlv':'[encoding1,encoding2...]'}
    dir_list = os.listdir(SAMPLE_DIR)
    for i in range(0, len(dir_list)):
        path = os.path.join(SAMPLE_DIR, dir_list[i])
        if os.path.isdir(path):
            if not dir_list[i] in known_face_encodings.keys():
                print('\nAdd new person: ' + dir_list[i] + '\n')
                known_face_encodings[dir_list[i]] = []
            image_list = os.listdir(path)
            for j in range(0, len(image_list)):
                if j > len(known_face_encodings[dir_list[i]]
                           ) - 1:  # new image id > history images num, encode
                    image_path = os.path.join(path, image_list[j])
                    print('Add new image, encoding it: ' + image_path)
                    image = face_recognition.load_image_file(image_path)
                    image_encoding = face_recognition.face_encodings(image)[0]
                    known_face_encodings[dir_list[i]].append(image_encoding)
                else:  # the old image, no encoding
                    pass

    # store the pkl file
    output = open(ENCODING_FILE_PATH, 'wb')
    # # Pickle dictionary using protocol 0.
    pickle.dump(known_face_encodings, output)
    output.close()

# 连接到PLC server


def connectToPlcController(plc_sock, HOST, PORT):
    plc_sock.connect((HOST, PORT))
    print('connect')


# 向web发送识别结果


def sendRecogResult(conn):
    msg['cmd'] = 130
    msg['ack'] = 123456
    msg_json = json.dumps(msg)
    print(msg_json)
    bs = bytes(msg_json + '\n', encoding="utf8")
    conn.send(bs)


def getUpdateMsgThread():
    global needUpdate
    update_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    update_sock.bind((LOCAL_HOST, UPDATE_PORT))
    update_sock.listen(1)
    conn, addr = update_sock.accept()
    print('Connected by', addr)
    while 1:
        bytes_data = conn.recv(100)
        if bytes_data:
            str_data = str(bytes_data)
            print(str_data)
            if str_data.find('134') != -1:
                needUpdate = True


# Initialize some variables
face_locations = []
face_encodings = []
known_face_encodings = {}


def run():
    process_this_frame = 0
    last_recog_id = ""
    # known_face_encodings = load_encode_image()

    global needUpdate
    # 启动子线程 在子线程中接收人脸库更新的消息
    updateThread = threading.Thread(
        target=getUpdateMsgThread, name="接收人脸库更新消息的线程")
    updateThread.start()

    # 等待web连接
    push_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    push_sock.bind((LOCAL_HOST, PUSH_PORT))
    push_sock.listen(1)
    conn, addr = push_sock.accept()

    while True:
        if needUpdate:
            # known_face_encodings = load_encode_image()
            # encode and store
            encode_store_file()
            # got know_face_encodings
            needUpdate = False

        # recover know_face_encoding
        # print(os.getcwd())
        # os.chdir(os.path.dirname(os.getcwd()))
        pkl_file = open(ENCODING_FILE_PATH, 'rb')
        known_face_encodings = pickle.load(pkl_file)
        pkl_file.close()

        # Grab a single frame of video
        ret, frame = video_capture.read()
        if not ret:
            continue
        # Resize frame of video to 1/4 size for faster face recognition processing
        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)

        # Convert the image from BGR color (which OpenCV uses) to RGB color (which face_recognition uses
        rgb_small_frame = small_frame[:, :, ::-1]

        # Only process every other frame of video to save time
        process_this_frame = (process_this_frame + 1) % 2

        # 显示实时画面  测试用
        cv2.imshow('Video', frame)
        cv2.waitKey(1)

        if process_this_frame == 0:
            start_time = int(round(time.time() * 1000))
            # Find all the faces and face encodings in the current frame of video
            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_encodings = face_recognition.face_encodings(
                rgb_small_frame, face_locations)

            face_num = len(face_locations)

            allow_pass = False
            # 如果未检测到人脸则处理下一帧
            if face_num == 0:
                continue

            msg['faceNumber'] = face_num
            msg['data'] = []

            # 判断识别图片中的人脸id
            for face_encoding in face_encodings:
                # See if the face is a match for the known face(s)
                for face_id in known_face_encodings:
                    distances = list(
                        face_recognition.face_distance(
                            known_face_encodings[face_id], face_encoding))

                    if min(distances) <= 0.5:
                        face = {}
                        face['id'] = face_id
                        face['compare'] = 1 - min(distances)
                        msg['data'].append(face)
                        allow_pass = True
                        print(face_id)
                        break

            end_time = int(round(time.time() * 1000))

            usage_time = end_time - start_time
            print('识别到' + str(face_num) + '张人脸' + ' 耗时' + str(usage_time) +
                  'ms')

            # 控制plc开门
            if allow_pass:
                file_name = 'ok_' + CAMERA_NAME + '_' + str(end_time) + '.jpg'
                msg['type'] = 1
                print('合法')
                if last_recog_id != face['id']:
                    # plc_sock.send(b'\x01')
                    last_recog_id = face['id']
                    print("open the door")
                else:
                    print("与上次识别到的id相同  不重复开门")
            else:
                file_name = 'warn_' + CAMERA_NAME + '_' + str(end_time) + '.jpg'
                msg['type'] = 0
                print('非法')

            # 将人脸图片保存  并将路径填入msg中

            file_path = PICTURE_SAVE_DIR + os.path.sep + file_name
            cv2.imwrite(file_path, frame)

            msg['filePath'] = file_path

            # 向web端发送识别结果
            sendRecogResult(conn)


if __name__ == '__main__':
    run()
    # Release handle to the webcam
    plc_sock.close()
    video_capture.release()
    cv2.destroyAllWindows()

# encode_store_file()