import time
import cv2
from EurusEdu import EurusControl, EurusCamera

class PID:
    def __init__(self, p, i, d):
        self.p = p
        self.i = i
        self.d = d
        self.integral = 0
        self.prev_error = 0
        self.output = 0

    def update_control(self, error):
        self.integral += error
        derivative = error - self.prev_error
        self.output = self.p * error + self.i * self.integral + self.d * derivative
        self.prev_error = error

    def get_control(self):
        return self.output

def constrain(value, threshold):
    if value > threshold:
        value = threshold
    if value < -threshold:
        value = -threshold
    return value


def simple_spin_search(drone, cam, enemy_color, hover_z=0.8):
    print("Начинаем поиск дрона по кругу...")
    for _ in range(4):
        drone.move_in_body_frame(x=0, y=0, z=hover_z, yaw=90)
        start_time = time.time()
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
                            print("Нашел живого вражеского дрона при кручении!")
                            # Возвращаем True, а ПИД-регулятор в главном цикле его довернет и выстрелит
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
    enemy_x = None

    if not targets_data or "all_objects" not in targets_data:
        return enemy_target, enemy_drone, allied_target, dead_drone, enemy_x

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
                    enemy_x = cx
                else:
                    enemy_target = True
                    enemy_x = cx
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
            
    return enemy_target, enemy_drone, allied_target, dead_drone, enemy_x


def main():
    medkit_input = input("Введите номер аптечки (например 10): ")
    medkit_id = int(medkit_input.strip()) if medkit_input.strip() else 10
    
    enemy_color = input("Введите цвет врага (red/blue): ").strip().lower()
    my_color = "blue" if enemy_color == "red" else "red"

    patrol_markers = [
        {"id": 515, "z": 1.0, "speed": 0.12, "yaw": 0},
        {"id": 525, "z": 1.0, "speed": 0.12, "yaw": -45},
        {"id": 381, "z": 1.0, "speed": 0.12, "yaw": 90},
        {"id": 165, "z": 1.0, "speed": 0.12, "yaw": 90},
        {"id": 59,  "z": 1.0, "speed": 0.12, "yaw": 0},
        {"id": 50,  "z": 1.0, "speed": 0.12, "yaw": 315},
        {"id": 170, "z": 1.0, "speed": 0.12, "yaw": 270},
        {"id": 386, "z": 1.0, "speed": 0.12, "yaw": 270}
    ]

    cam = EurusCamera("192.168.1.17", 8001)
    drone = EurusControl("192.168.1.17", 65432)

    drone.start_game(start_game=True, team_color=my_color)
    cam.connect()
    
    cam.start_stream()
    print("Камера включена.")

    print("Взлет...")
    drone.arm()
    drone.takeoff(1.0, speed=0.12)
    time.sleep(5)

    drone.aruco_map_navigation(state=True, fly_in_borders=True)
    time.sleep(3)

    print("Начинаем патрулирование!")

    target_index = 0
    last_move_time = 0
    last_shot_time = 0
    is_healing = False
    
    # Инициализация ПИД-регулятора
    pid_yaw = PID(0.005, 0.0, 0.001)

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
                    time.sleep(1)
                    drone.move_to_marker(
                        marker_id=marker_data["id"], 
                        z=marker_data["z"], 
                        speed=marker_data["speed"], 
                        yaw=marker_data["yaw"]
                    )
                    
                    target_index = (target_index + 1) % len(patrol_markers)
                    last_move_time = time.time() 

            # --- ЛОГИКА КАМЕРЫ И ВЫСТРЕЛА (С ПИД НАВЕДЕНИЕМ) ---
            ret, frame = cam.read()
            if ret:
                image_width = frame.shape[1]
                target_center_x = image_width / 2
                
                targets = cam.get_detection(blocking=False)
                enemy_target, enemy_drone, allied_target, dead_drone, enemy_x = draw_targets(frame, targets, enemy_color, my_color)
                
                if dead_drone and not is_healing:
                    print("Вижу мертвого (белого) дрона! Скипаем на следующую метку.")
                    last_move_time = 0
                
                elif (enemy_target or enemy_drone) and (enemy_x is not None):
                    # --- ПИД НАВЕДЕНИЕ ПЕРЕД ВЫСТРЕЛОМ ---
                    error = target_center_x - enemy_x
                    
                    if abs(error) < 20: 
                        # Цель соосна (в центре)
                        drone.set_velocity(vx=0.0, vy=0.0, vz=0.0, yaw_rate=0.0)
                        if time.time() - last_shot_time > 1.0:
                            print("Враг соосно! ВЫСТРЕЛ!")
                            drone.laser_shot()
                            last_shot_time = time.time()
                            
                        # Сбрасываем таймер движения, чтобы дрон оставался на месте и не улетел на патруль
                        last_move_time = time.time()
                    else:
                        # Цель не в центре, доворачиваем с помощью ПИД
                        pid_yaw.update_control(error)
                        yaw_vel = pid_yaw.get_control()
                        yaw_vel = constrain(yaw_vel, 1.0)
                        print(f"Доворот на цель... Ошибка: {error:.1f}, yaw_vel: {yaw_vel:.2f}")
                        
                        drone.set_velocity(vx=0.0, vy=0.0, vz=0.0, yaw_rate=yaw_vel)
                        # Сбрасываем таймер движения, чтобы дрон продолжал целиться
                        last_move_time = time.time()

                elif allied_target and not is_healing:
                    print("Попадание подтверждено! Медленно крутимся и ищем дрона...")
                    current_hover_z = patrol_markers[max(0, target_index - 1)]["z"]
                    
                    found = simple_spin_search(drone, cam, enemy_color, hover_z=current_hover_z)
                    if found:
                        # Нашли врага - сброс таймера, в следующем кадре отработает ПИД-наведение
                        last_move_time = time.time()
                    
                    last_move_time = time.time()

                # cv2.imshow("Drone Patrol", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("Остановлено.")
    finally:
        print("Посадка...")
        drone.set_velocity(vx=0.0, vy=0.0, vz=0.0, yaw_rate=0.0)
        drone.land()
        time.sleep(3)
        cam.stop_stream()
        cam.disconnect()
        drone.disconnect()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
