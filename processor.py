from deepface import DeepFace
from paddleocr import PaddleOCR
import cv2
import os
import numpy as np
import tensorflow as tf
import paddle
from utils import load_config
from datetime import datetime
import traceback

class ImageProcessor:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self._initialize_models()  # 每次处理时初始化模型

    def _initialize_models(self):
        """为每个进程初始化独立的模型"""
        try:
            # 检查 TensorFlow GPU 可用性 (DeepFace)
            gpus = tf.config.list_physical_devices('GPU')
            if self.config['deepface']['use_gpu'] and len(gpus) == 0:
                self.logger.warning("GPU requested but not available for DeepFace")
            elif len(gpus) > 0:
                self.logger.info(f"GPU available for DeepFace: {gpus}")
            else:
                self.logger.info("Running DeepFace on CPU as per config")

            # 检查 PaddlePaddle GPU 可用性 (PaddleOCR)
            paddle_gpus = paddle.device.cuda.device_count()
            if self.config['ocr']['use_gpu'] and paddle_gpus == 0:
                self.logger.warning("GPU requested but not available for PaddleOCR")
            elif paddle_gpus > 0:
                self.logger.info(f"GPU available for PaddleOCR: {paddle_gpus} devices")
            else:
                self.logger.info("Running PaddleOCR on CPU as per config")

            # 初始化 PaddleOCR
            self.ocr = PaddleOCR(
                use_gpu=self.config['ocr']['use_gpu'],
                use_angle_cls=True,
                lang='en',
                ocr_version='PP-OCRv4'
            )
            self.logger.info("PaddleOCR initialized with use_angle_cls=True")
        except Exception as e:
            self.logger.error(f"Model initialization failed: {str(e)}\n{traceback.format_exc()}")
            raise

    def process_faces(self, image, image_path, logger):
        try:
            start_time = datetime.now()
            logger.info(f"Starting face processing for {image_path} at {start_time}")

            representations = DeepFace.represent(
                img_path=image,
                model_name=self.config['deepface']['model'],
                detector_backend=self.config['deepface']['detector'],
                align=self.config['deepface']['alignment'],
                enforce_detection=False,  # 避免检测失败中断
                expand_percentage=self.config['deepface']['expand_percentage']
            )

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.info(f"Face processing completed for {image_path} at {end_time}, "
                       f"found {len(representations)} faces, took {duration:.3f} seconds")

            embeddings = []
            for face_idx, rep in enumerate(representations):
                confidence = rep.get('face_confidence', 0.0)
                if confidence >= self.config['deepface']['detect_confidence']:
                    embedding = np.array(rep["embedding"])
                    embeddings.append((embedding, confidence))
                    
                    if self.config['deepface']['debug']:
                        facial_area = rep['facial_area']
                        self._draw_face(image, facial_area, confidence)
                        draw_end_time = datetime.now()
                        logger.debug(f"Drawing face {face_idx} completed for {image_path} at {draw_end_time}")

            if self.config['deepface']['debug'] and representations:
                self._save_debug_image(image_path, image, 'face')

            return embeddings
        except Exception as e:
            logger.error(f"Face processing error for {image_path}: {str(e)}\n{traceback.format_exc()}")
            return []

    # process_bibs 和其他方法保持不变，仅增强错误日志
    def process_bibs(self, image, image_path, logger):
        try:
            result = self.ocr.ocr(image)
            bibs = set()
            if result and result[0]:
                for line in result[0]:
                    text = line[1][0]
                    confidence = line[1][1]
                    if (text.isdigit() and 
                        self.config['ocr']['min_size'] <= len(text) <= self.config['ocr']['max_size'] and 
                        confidence >= self.config['ocr']['confidence']):
                        bibs.add((text, confidence))
                        
                        if self.config['ocr']['debug']:
                            self._draw_bib(image, line)

            if self.config['ocr']['debug'] and result and result[0]:
                self._save_debug_image(image_path, image, 'ocr')

            return bibs
        except Exception as e:
            logger.error(f"Bib processing error for {image_path}: {str(e)}\n{traceback.format_exc()}")
            return set()

    def _draw_face(self, img, facial_area, confidence):
        """绘制人脸框和置信度，使用绿色细线"""
        x, y, w, h = facial_area['x'], facial_area['y'], facial_area['w'], facial_area['h']

        # 使用绿色细线绘制矩形框和文字
        cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 1)  # 绿色框，厚度 1
        text = f"{confidence:.2f}"
        cv2.putText(img, text, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 1)  # 绿色文字，厚度 1

    def _draw_bib(self, img, line):
        """绘制 bib 框和识别内容，使用黑色主色和白色描边"""
        points = line[0]
        x, y = int(points[0][0]), int(points[0][1])
        w, h = int(points[2][0] - x), int(points[2][1] - y)

        # 绘制矩形框：白色描边 + 黑色主框
        cv2.rectangle(img, (x, y), (x+w, y+h), (255, 255, 255), 3)  # 白色描边，厚度 3
        cv2.rectangle(img, (x, y), (x+w, y+h), (0, 0, 0), 1)       # 黑色主框，厚度 1

        # 绘制文字：白色描边 + 黑色主色
        text = f"{line[1][0]} ({line[1][1]:.2f})"
        cv2.putText(img, text, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 3)  # 白色描边，厚度 3
        cv2.putText(img, text, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 1)       # 黑色文字，厚度 1

    def _save_debug_image(self, image_path, img, debug_type):
        if debug_type == 'face':
            debug_dir = self.config['deepface']['debug_dir']
        else:  # ocr
            debug_dir = self.config['ocr']['debug_dir']

        debug_path = image_path.replace(self.config['photo_dir'], debug_dir)
        os.makedirs(os.path.dirname(debug_path), exist_ok=True)
        cv2.imwrite(debug_path, img)
