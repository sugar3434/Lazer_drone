import time
import cv2
import numpy as np
from EurusEdu import EurusControl, EurusCamera

def draw_targets(frame, targets_data, enemy_color):
    """
    Отрисовка рамок и меток для обнаруженных объектов.
    """
    if not targets_data or "all_objects" not in targets_data:
        return

    # Проверка актуальности данных
    data_age = time.time() - targets_data.get("received_at", time.time())
    if data_age > 0.5:
        return 

    for target in targets_data["all_objects"]:
        try:
            cx = target['x'] 
            cy = target['y'] 
            w = target['w']  
            h = target['h']  
            cls_name = target['class'].lower()
            conf = target.get('conf', 0.0)

            top_left_x = int(cx - w / 2)
            top_left_y = int(cy - h / 2)
            bottom_right_x = int(cx + w / 2)
            bottom_right_y = int(cy + h / 2)

            color = (0, 255, 0) # По умолчанию зеленый
            if "red" in cls_name:
                color = (0, 0, 255) 
            elif "blue" in cls_name:
                color = (255, 0, 0) 
            
            # Выделяем рамку цветом если это враг
            if enemy_color in cls_name:
                color = (0, 255, 255) # Желтый для подсветки вражеской цели

            cv2.rectangle(frame, (top_left_x, top_left_y), (bottom_right_x, bottom_right_y), color, 2)
            
            label = f"{cls_name} {conf:.2f} W:{int(w)} H:{int(h)}"
            cv2.putText(frame, label, (top_left_x, top_left_y - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        except KeyError:
            continue

def main():
    # Запрос параметров
    medkit_input = input("Введите номера меток аптечек (через запятую, например 10,11): ")
    medkit_markers = [int(m.strip()) for m in medkit_input.split(",") if m.strip()]
    
    enemy_color = input("Введите цвет врага (red/blue): ").strip().lower()
    my_color = "blue" if enemy_color == "red" else "red"
    
    # Целевой класс для обнаружения нейросетью (например, "red target")
    enemy_target_class = f"{enemy_color} target"
    
    speed_input = input("Введите скорость полета (например 0.5): ")
    try:
        flight_speed = float(speed_input)
    except ValueError:
        flight_speed = 0.5
        print("Некорректная скорость, установлена скорость по умолчанию: 0.5")
    
    # Инициализация и подключение к дрону
    drone = EurusControl("192.168.1.17", 65432)
    drone.connect()
    time.sleep(1)
    
    # Инициализация и подключение к камере
    cam = EurusCamera("192.168.1.17", 8001)
    try:
        cam.connect()
        cam.start_stream()
        time.sleep(1)
    except Exception as e:
        print(f"Внимание: Не удалось подключиться к камере: {e}")
    
    # Старт игры
    try:
        drone.start_game(start_game=True, command_color=my_color)
    except TypeError:
        drone.start_game()
    
    # Взлет с указанной скоростью
    print(f"Взлет на высоту 1.5м со скоростью {flight_speed}...")
    drone.arm()
    drone.takeoff(1.5, speed=flight_speed)
    time.sleep(6) # Ожидание стабилизации
    
    print("Включение навигации по ArUco маркерам...")
    drone.aruco_map_navigation(state=True, fly_in_borders=True)
    time.sleep(1)
    
    print("Миссия начата! Для выхода нажмите 'q' в окне видео или Ctrl+C в консоли.")
    
    try:
        while True:
            # 1.0 Постоянная проверка состояния (Батарея, жизни)
            telemetry = drone.get_telemetry()
            if telemetry is not None:
                is_alive = telemetry.get("is_alive", True)
                battery = telemetry.get("battery", {}).get("percentage", 100)
                
                # Если дрон "убит", летим на базу (аптечку)
                if not is_alive:
                    if medkit_markers:
                        medkit_id = medkit_markers[0]
                        print(f"Дрон убит! Возврат на зону аптечки (маркер {medkit_id}) со скоростью {flight_speed}...")
                        drone.move_to_marker(medkit_id, 1.5, speed=flight_speed)
                        time.sleep(5)
                    continue

            # Получение кадра из камеры
            ret, frame = False, None
            try:
                ret, frame = cam.read()
            except Exception:
                pass
                
            # 1.1 Обнаружение вражеских дронов и отрисовка CV
            try:
                # Получаем данные о распознанных объектах
                targets = cam.get_detection(blocking=False)
                
                # Отрисовываем рамки, если кадр успешно получен
                if ret and frame is not None:
                    if targets:
                        draw_targets(frame, targets, enemy_color)
                    cv2.imshow("Drone Feed + YOLO", frame)
                
                # Логика стрельбы при обнаружении нужного таргета
                if targets and "all_objects" in targets:
                    for target in targets["all_objects"]:
                        cls_name = target.get('class', '').lower()
                        # Если класс содержит, например, "red target" или просто цвет врага
                        if enemy_target_class in cls_name or enemy_color in cls_name:
                            print(f"Вражеская цель ({cls_name}) обнаружена! Огонь!")
                            drone.laser_shot()
                            break
            except Exception as e:
                pass
            
            # Обработка нажатия клавиш OpenCV
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("Выход по нажатию 'q'.")
                break
            
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\nМиссия прервана пользователем.")
    finally:
        print("Посадка...")
        drone.land()
        time.sleep(3)
        print("Отключение...")
        drone.disconnect()
        try:
            cam.stop_stream()
            cam.disconnect()
            cv2.destroyAllWindows()
        except:
            pass

if __name__ == "__main__":
    main()
