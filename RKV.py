import time
import cv2
from EurusEdu import EurusControl, EurusCamera

def simple_spin_search(drone, cam, enemy_color, hover_z=0.8):
    print("Начинаем поиск дрона по кругу...")
    for _ in range(4):
        drone.move_in_body_frame(x=0, y=0, z=hover_z, yaw=90)
        start_time = time.time()
        last_shot_time = 0
        while time.time() - start_time < 2.0:
            ret, frame = cam.read()
            if not ret:
                time.sleep(0.05)
                continue
                
            targets = cam.get_detection(blocking=False)
            if not targets or "all_objects" not in targets:
                time.sleep(0.05)
                continue
                
            for obj in targets["all_objects"]:
                try:
                    cls_name = obj['class'].lower()
                    if "drone" in cls_name:
                        if "white" in cls_name:
                            print("Враг уже мертв (белый)! Прерываем поиск.")
                            return False 
                        elif enemy_color in cls_name:
                            print("Нашел живого вражеского дрона!")
                            if time.time() - last_shot_time > 1.0:
                                drone.laser_shot()
                                print("ВЫСТРЕЛ!")
                                last_shot_time = time.time()
                                return True 
                except Exception as e:
                    print(f"Ошибка чтения цели в поиске: {e}")
            time.sleep(0.05)
    print("Поиск завершен, никого не нашли. Летим дальше.")
    return False


def draw_targets(frame, targets_data, enemy_color, my_color):
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
            if "white" in cls_name:
                color = (255, 255, 255)
                dead_drone = True
            elif enemy_color in cls_name:
                color = (0, 255, 255)
                if "drone" in cls_name:
                    enemy_drone = True
                else:
                    enemy_target = True
            elif my_color in cls_name:
                color = (255, 255, 0)
                if "target" in cls_name:
                    allied_target = True

            x1, y1 = int(cx - w/2), int(cy - h/2)
            x2, y2 = int(cx + w/2), int(cy + h/2)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, cls_name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        except Exception as e:
            pass
            
    return enemy_target, enemy_drone, allied_target, dead_drone


def main():
    medkit_input = input("Введите номер аптечки (например 10): ")
    medkit_id = int(medkit_input.strip()) if medkit_input.strip() else 10
    
    enemy_color = input("Введите цвет врага (red/blue): ").strip().lower()
    my_color = "blue" if enemy_color == "red" else "red"

    patrol_markers = [
        {"id": 515, "z": 1.0, "speed": 0.2, "yaw": 90},
        {"id": 525, "z": 1.0, "speed": 0.2, "yaw": 45},
        {"id": 381, "z": 1.0, "speed": 0.2, "yaw": 0},
        {"id": 165, "z": 1.0, "speed": 0.2, "yaw": 0},
        {"id": 59,  "z": 1.0, "speed": 0.2, "yaw": 270},
        {"id": 50,  "z": 1.0, "speed": 0.2, "yaw": 225},
        {"id": 170, "z": 1.0, "speed": 0.2, "yaw": 180},
        {"id": 386, "z": 0.8, "speed": 0.2, "yaw": 180}
    ]

    cam = EurusCamera("192.168.1.17", 8001)
    drone = EurusControl("192.168.1.17", 65432)

    drone.start_game(start_game=True, team_color=my_color)
    cam.connect()
    
    # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Включаем стрим камеры!
    cam.start_stream()
    print("Камера включена.")

    print("Взлет...")
    drone.arm()
    drone.takeoff(1.0, speed=0.4)
    time.sleep(5)

    drone.aruco_map_navigation(state=True, fly_in_borders=True)
    time.sleep(3)

    print("Начинаем патрулирование!")

    target_index = 0
    last_move_time = 0
    last_shot_time = 0
    is_healing = False

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
                    marker_data = patrol_markers[target_index]
                    print(f"Летим к метке {marker_data['id']}")
                    
                    # Летим к метке (блокирующий вызов)
                    drone.move_to_marker(
                        marker_id=marker_data["id"], 
                        z=marker_data["z"], 
                        speed=marker_data["speed"], 
                        yaw=marker_data["yaw"]
                    )
                    
                    target_index = (target_index + 1) % len(patrol_markers)
                    last_move_time = time.time() 
                    # Следующие 8 секунд дрон висит на точке и смотрит в камеру

            # --- ЛОГИКА КАМЕРЫ И ВЫСТРЕЛА ---
            ret, frame = cam.read()
            if ret:
                targets = cam.get_detection(blocking=False)
                enemy_target, enemy_drone, allied_target, dead_drone = draw_targets(frame, targets, enemy_color, my_color)
                
                if dead_drone and not is_healing:
                    print("Вижу мертвого (белого) дрона! Скипаем на следующую метку.")
                    last_move_time = 0
                
                elif (enemy_target or enemy_drone) and (time.time() - last_shot_time > 1.0):
                    print("Враг обнаружен! Выстрел!")
                    drone.laser_shot()
                    last_shot_time = time.time()

                elif allied_target and not is_healing:
                    print("Попадание подтверждено! Медленно крутимся и ищем дрона...")
                    
                    # Берем высоту из предыдущего маркера (к которому мы только что прилетели)
                    current_hover_z = patrol_markers[max(0, target_index - 1)]["z"]
                    
                    simple_spin_search(drone, cam, enemy_color, hover_z=current_hover_z)
                    
                    # Обновляем таймер, чтобы постоять на точке еще немного после кручения
                    last_move_time = time.time()

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
