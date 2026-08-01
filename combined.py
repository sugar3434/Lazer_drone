import time
import cv2
from EurusEdu import EurusControl, EurusCamera

def draw_targets(frame, targets_data, enemy_color, my_color):
    """
    Простая отрисовка целей и проверка на наличие врагов/союзников.
    Возвращает 4 флага: (вражеская мишень, вражеский дрон, союзная мишень, мертвый дрон)
    """
    enemy_target = False
    enemy_drone = False
    allied_target = False
    dead_drone = False

    if not targets_data or "all_objects" not in targets_data:
        return enemy_target, enemy_drone, allied_target, dead_drone

    for target in targets_data["all_objects"]:
        try:
            cx, cy, w, h = target['x'], target['y'], target['w'], target['h']
            cls_name = target['class'].lower()
            
            if "target" not in cls_name and "drone" not in cls_name:
                continue

            color = (0, 255, 0)
            
            # Если мигает белым (мертвый)
            if "white" in cls_name:
                color = (255, 255, 255) # Белый
                dead_drone = True
            
            # Если это враг
            elif enemy_color in cls_name:
                color = (0, 255, 255) # Желтый для врага
                if "drone" in cls_name:
                    enemy_drone = True
                else:
                    enemy_target = True
            
            # Если это наша (союзная) мишень - значит мы по ней уже попали!
            elif my_color in cls_name:
                color = (255, 255, 0) # Голубой для своих
                if "target" in cls_name:
                    allied_target = True

            # Рисуем рамку
            x1, y1 = int(cx - w/2), int(cy - h/2)
            x2, y2 = int(cx + w/2), int(cy + h/2)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, cls_name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        except:
            continue
            
    return enemy_target, enemy_drone, allied_target, dead_drone

def main():
    medkit_input = input("Введите номер аптечки (например 10): ")
    medkit_id = int(medkit_input.strip()) if medkit_input.strip() else 10
    
    enemy_color = input("Введите цвет врага (red/blue): ").strip().lower()
    my_color = "blue" if enemy_color == "red" else "red"

    # Просто список меток для полета
    patrol_markers = [563, 575, 383, 167, 11, 0, 168, 384]

    cam = EurusCamera("192.168.1.17", 8001)
    drone = EurusControl("192.168.1.17", 65432)

    print("Подключаемся...")
    drone.connect()
    cam.connect()
    cam.start_stream()
    time.sleep(1)
    
    try:
        drone.start_game(start_game=True, command_color=my_color)
    except:
        pass

    print("Взлет...")
    drone.arm()
    drone.takeoff(1.0, speed=0.4)
    time.sleep(5)

    drone.aruco_map_navigation(state=True, fly_in_borders=True)
    time.sleep(1)

    print("Начинаем патрулирование!")

    target_index = 0
    last_move_time = 0
    last_shot_time = 0
    is_healing = False
    has_spun = False

    try:
        while True:
            # --- ЛОГИКА АПТЕЧКИ ---
            telemetry = drone.get_telemetry()
            if telemetry is not None:
                is_alive = telemetry.get("is_alive", True)
                
                if not is_alive and not is_healing:
                    print(f"УБИЛИ! Летим на аптечку {medkit_id}")
                    drone.move_to_marker(medkit_id, 1.0, speed=0.4)
                    is_healing = True
                
                if is_alive and is_healing:
                    print("Ожили! Возвращаемся к патрулю.")
                    is_healing = False
                    last_move_time = 0

            # --- ЛОГИКА ДВИЖЕНИЯ ---
            if not is_healing:
                if time.time() - last_move_time > 8.0:
                    marker = patrol_markers[target_index]
                    print(f"Летим к метке {marker}")
                    
                    drone.move_to_marker(marker, 1.0, speed=0.4)
                    
                    target_index += 1
                    if target_index >= len(patrol_markers):
                        target_index = 0
                        
                    last_move_time = time.time()
                    has_spun = False

            # --- ЛОГИКА КАМЕРЫ, ВЫСТРЕЛА И КРУЧЕНИЯ ---
            ret, frame = cam.read()
            if ret:
                targets = cam.get_detection(blocking=False)
                if targets:
                    enemy_target, enemy_drone, allied_target, dead_drone = draw_targets(frame, targets, enemy_color, my_color)
                    
                    # Если увидели белого (мертвого) дрона - сразу на некст метку!
                    if dead_drone and not is_healing:
                        print("Вижу мертвого (белого) дрона! Скипаем на следующую метку.")
                        last_move_time = 0
                    
                    # Стреляем по живому врагу
                    elif (enemy_target or enemy_drone) and (time.time() - last_shot_time > 1.0):
                        print("Враг обнаружен! Выстрел!")
                        drone.laser_shot()
                        last_shot_time = time.time()

                    # Если мишень союзная (попали) и еще не крутились
                    elif allied_target and not has_spun and not is_healing:
                        print("Попадание подтверждено! Медленно крутимся и ищем дрона...")
                        has_spun = True
                        
                        spin_interrupted = False
                        
                        # Кручение 4 раза по 90 градусов
                        for _ in range(4):
                            if spin_interrupted:
                                break
                                
                            drone.move_in_body_frame(x=0, y=0, z=1.0, yaw=90)
                            
                            spin_timer = time.time()
                            while time.time() - spin_timer < 2.0:
                                s_ret, s_frame = cam.read()
                                if s_ret:
                                    s_targets = cam.get_detection(blocking=False)
                                    if s_targets:
                                        _, e_drone, _, d_drone = draw_targets(s_frame, s_targets, enemy_color, my_color)
                                        
                                        # Если во время кручения увидели белого дрона - прерываем кручение!
                                        if d_drone:
                                            print("Вражеский дрон мертв (белый)! Прерываем кручение, летим дальше.")
                                            spin_interrupted = True
                                            break
                                            
                                        # Если живой дрон - стреляем
                                        if e_drone and (time.time() - last_shot_time > 1.0):
                                            print("Вижу вражеского дрона при кручении! Выстрел!")
                                            drone.laser_shot()
                                            last_shot_time = time.time()
                                            
                                    cv2.imshow("Drone Patrol", s_frame)
                                    cv2.waitKey(1)
                                time.sleep(0.05)
                        
                        # Завершили или прервали кручение - летим на следующую метку
                        print("Кручение завершено/прервано. Летим дальше.")
                        last_move_time = 0

                cv2.imshow("Drone Patrol", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("Остановлено.")
    finally:
        print("Посадка...")
        drone.land()
        time.sleep(3)
        cam.stop_stream()
        cam.disconnect()
        drone.disconnect()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
