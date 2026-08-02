import time
import cv2
from EurusEdu import EurusControl, EurusCamera

# КЛАССЫ И ФУНКЦИИ ДЛЯ ПИД-РЕГУЛЯТОРА 
class PIDYaw:
    def __init__(self, kp=0.005, ki=0.0, kd=0.001):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.integral = 0.0
        self.prev_error = 0.0
        self.control = 0.0
        
    def update_control(self, error):
        self.integral += error
        derivative = error - self.prev_error
        self.prev_error = error
        # Ограничиваем интегральную составляющую, чтобы избежать windup
        self.integral = max(-100.0, min(100.0, self.integral)) 
        self.control = (self.kp * error) + (self.ki * self.integral) + (self.kd * derivative)
        
    def get_control(self):
        return self.control

def constrain(value, max_limit):
    return max(-max_limit, min(value, max_limit))

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
        except:
            continue
            
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
        {"id": 386, "z": 0.8, "speed": 0.4, "yaw": 180}
    ]

    cam = EurusCamera("192.168.1.17", 8001)
    drone = EurusControl("192.168.1.17", 65432)

    # Инициализация ПИД-регулятора для наводки
    pid_yaw = PIDYaw(kp=0.005, ki=0.001, kd=0.001)

    drone.start_game(start_game=True, team_color=my_color)

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
                    marker_data = patrol_markers[target_index]
                    marker_id = marker_data["id"]
                    print(f"Летим к метке {marker_id}")
                    
                    drone.move_to_marker(
                        marker_id=marker_id, 
                        z=marker_data["z"], 
                        speed=marker_data["speed"], 
                        yaw=marker_data["yaw"]
                    )
                    
                    target_index += 1
                    if target_index >= len(patrol_markers):
                        target_index = 0
                        
                    last_move_time = time.time()
                    has_spun = False

            # --- ЛОГИКА КАМЕРЫ, НАВОДКИ И ВЫСТРЕЛА ---
            ret, frame = cam.read()
            if ret:
                targets = cam.get_detection(blocking=False)
                if targets:
                    enemy_target, enemy_drone, allied_target, dead_drone = draw_targets(frame, targets, enemy_color, my_color)
                    
                    if dead_drone and not is_healing:
                        print("Вижу мертвого (белого) дрона! Скипаем на следующую метку.")
                        last_move_time = 0
                    
                    # --- НОВЫЙ БЛОК: НАВОДКА И ВЫСТРЕЛ ПО ВРАЖЕСКОМУ ДРОНУ ---
                    elif enemy_drone and not is_healing:
                        image_width = frame.shape[1]
                        target_center_x = image_width / 2
                        
                        # Ищем конкретного вражеского дрона в кадре для точного расчета X
                        drone_box = None
                        for obj in targets["all_objects"]:
                            if "drone" in obj['class'].lower() and enemy_color in obj['class'].lower():
                                drone_box = obj
                                break
                                
                        if drone_box:
                            current_x = drone_box['x']
                            error = target_center_x - current_x
                            
                            if abs(error) < 20:
                                print("Цель захвачена!")
                                drone.set_vel_xy_yaw(0.0, 0.0, 0.0) # Останавливаем поворот
                                if time.time() - last_shot_time > 0.5:
                                    print("Выстрел!")
                                    drone.laser_shot()
                                    last_shot_time = time.time()
                            else:
                                pid_yaw.update_control(error)
                                yaw_vel = pid_yaw.get_control()
                                yaw_vel = constrain(yaw_vel, 1.0) # Ограничиваем скорость поворота
                                print(f"Корректировка: {yaw_vel:.2f}, Ошибка: {error:.1f}")
                                drone.set_vel_xy_yaw(0.0, 0.0, yaw_vel)
                                
                    elif enemy_target and (time.time() - last_shot_time > 1.0):
                        # Если это просто мишень (не дрон), стреляем без сложной наводки
                        print("Вражеская мишень обнаружена! Выстрел!")
                        drone.laser_shot()
                        last_shot_time = time.time()

                    # Если мишень союзная (попали) и еще не крутились
                    elif allied_target and not has_spun and not is_healing:
                        print("Попадание подтверждено! Медленно крутимся и ищем дрона...")
                        has_spun = True
                        
                        # Сбрасываем скорость yaw перед кручением
                        drone.set_vel_xy_yaw(0.0, 0.0, 0.0)
                        
                        spin_interrupted = False
                        
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
                                        
                                        if d_drone:
                                            print("Вражеский дрон мертв (белый)! Прерываем кручение.")
                                            spin_interrupted = True
                                            break
                                            
                                        if e_drone and (time.time() - last_shot_time > 1.0):
                                            print("Вижу вражеского дрона при кручении! Выстрел!")
                                            drone.laser_shot()
                                            last_shot_time = time.time()
                                            
                                    cv2.imshow("Drone Patrol", s_frame)
                                    cv2.waitKey(1)
                                time.sleep(0.05)
                        
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
        drone.set_vel_xy_yaw(0.0, 0.0, 0.0) # Сбрасываем скорости перед посадкой
        drone.land()
        time.sleep(3)
        cam.stop_stream()
        cam.disconnect()
        drone.disconnect()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
