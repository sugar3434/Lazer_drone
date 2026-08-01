import cv2
import time
from ultralytics import YOLO
from EurusEdu import EurusCamera

def main():
    print("Инициализация модели YOLO...")
    # Инициализация модели YOLO (максимально просто по либе)
    # Предполагается, что веса best.pt находятся в той же папке
    try:
        model = YOLO("best.pt")
    except Exception as e:
        print(f"Ошибка загрузки модели. Убедитесь, что best.pt существует: {e}")
        return

    print("Подключение к камере...")
    # Инициализация камеры дрона
    cam = EurusCamera("192.168.1.17", 8001) # Адрес по умолчанию для Orange Pi (или 10.42.0.1)
    
    is_eurus = True
    try:
        cam.connect()
        cam.start_stream()
        time.sleep(1)
        print("Камера дрона подключена успешно!")
    except Exception as e:
        print(f"Ошибка подключения к камере дрона: {e}")
        print("Попытка использования стандартной веб-камеры...")
        cam = cv2.VideoCapture(0) # Фолбэк на обычную веб-камеру
        is_eurus = False

    print("Запуск системы распознавания. Нажмите 'q' для выхода.")

    start_time = time.time()
    frame_count = 0

    try:
        while True:
            # Получение кадра в зависимости от типа камеры
            if is_eurus:
                ret, frame = cam.read()
            else:
                ret, frame = cam.read()
                
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            frame_count += 1
            fps = frame_count / (time.time() - start_time)

            # --- Использование библиотеки Ultralytics YOLO ---
            # Предсказание на полученном кадре (predict)
            results = model.predict(source=frame, show=False, verbose=False)
            
            # --- Отрисовка результатов (максимально просто) ---
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    cls = int(box.cls[0])
                    conf = float(box.conf[0])
                    class_name = model.names[cls].lower()
                    
                    # Задание: распознавание через yolo red_target и red_drone
                    if class_name in ['red_target', 'red_drone']:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        
                        # Выбор цвета
                        color = (0, 0, 255) if class_name == 'red_target' else (0, 165, 255)
                        
                        # Обычная рамка
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        
                        # Обычный текст
                        label = f"{class_name} {conf:.2f}"
                        cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                        
            # Вывод результата на экран
            cv2.imshow("YOLOv11 Tracker", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("Прервано пользователем.")
    finally:
        print("Остановка...")
        if is_eurus:
            try:
                cam.stop_stream()
                cam.disconnect()
            except:
                pass
        else:
            cam.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
