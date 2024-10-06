import json
import re
from geopy.distance import geodesic

#Скрипт парсинга и конвертации html данных маршрутов и останов в формат geojason

# Пользовательский ввод для указания маршрута и города
city_name = input("Введите номер города: ")
route_name = input("Введите номер маршрута: ")

# Чтение содержимого файла
file_path = '../source_data/15_27.txt'  # Путь к файлу с данными
with open(file_path, 'r', encoding='utf-8') as file:
    file_content = file.read()

# 1. Извлечение всех LineString координат
line_string_pattern = re.compile(r'type:\s*"LineString",\s*coordinates:\s*\[(.*?)\]\s*}', re.DOTALL)
line_strings = line_string_pattern.findall(file_content)

# Преобразование координат в отдельные LineString объекты с direction
line_string_features = []
line_coords = []

for i, line in enumerate(line_strings):
    coordinates = re.findall(r'\[(\d+\.\d+),\s*(\d+\.\d+)\]', line)
    if coordinates:
        coords = [[float(lon), float(lat)] for lat, lon in coordinates]
        line_coords.append(coords)
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coords
            },
            "properties": {
                "route": route_name,
                "direction": i, # direction = 0 для первого блока, 1 для второго и т.д.
                "type": 0,
                "segment_info": ''

            }
        }
        line_string_features.append(feature)

# 2. Извлечение всех Point координат и их hintContent
point_pattern = re.compile(r'coordinates:\s*\[(\d+\.\d+),\s*(\d+\.\d+)\].*?hintContent:\s*\'(.*?)\'', re.DOTALL)
points = point_pattern.findall(file_content)

# Функция для расчета расстояния между двумя точками
def calculate_distance(coord1, coord2):
    return geodesic(coord1, coord2).meters

# Преобразование точек для GeoJSON формата
points_features = []
hint_counter = {}  # Счетчик для хранения количества встреченных hintContent

# Группировка точек по направлениям (direction)
points_by_direction = {0: [], 1: []}

# Разбиваем точки на два направления: 0 и 1
for point in points:
    coord = [float(point[1]), float(point[0])]
    hint_content = point[2]

    # Если hintContent уже встречался, увеличиваем счетчик
    if hint_content in hint_counter:
        hint_counter[hint_content] += 1
    else:
        hint_counter[hint_content] = 0  # Инициализируем первый элемент

    # Присвоение направления: 0 для первого, 1 для второго
    current_direction = hint_counter[hint_content] % 2

    # Добавляем точку в список по направлению
    points_by_direction[current_direction].append((coord, hint_content, current_direction))


# Обновленная функция для поиска сегмента между остановками с динамическим радиусом
def find_segment_between_stops(start_point, end_point, line_coords):
    start_coord = start_point[0]
    end_coord = end_point[0]
    segment_coords = []

    start_index = None
    end_index = None
    radius = 300  # Начальный радиус поиска

    # Динамическое увеличение радиуса поиска, если сегменты не найдены
    while start_index is None or end_index is None:
        for i, coord in enumerate(line_coords):
            if start_index is None and calculate_distance(coord, start_coord) <= radius:
                start_index = i
            if end_index is None and calculate_distance(coord, end_coord) <= radius:
                end_index = i

        # Увеличиваем радиус до 1000 метров максимум
        radius += 100
        if radius > 1500:
            break  # Остановить, если радиус слишком велик и не удается найти сегмент

    # Если нашли оба индекса, собираем сегмент
    if start_index is not None and end_index is not None and start_index < end_index:
        segment_coords = line_coords[start_index:end_index + 1]

    return segment_coords

# Максимальное допустимое расстояние между сегментами (в метрах)
MAX_SEGMENT_DISTANCE = 1500

# Обработка каждой группы точек по направлению
for direction, points_list in points_by_direction.items():
    for i in range(len(points_list) - 1):
        start_stop = points_list[i]
        end_stop = points_list[i + 1]

        # Условие: если следующий сегмент принадлежит другому направлению, пропускаем
        if start_stop[2] != end_stop[2]:
            continue

        # Поиск сегмента между двумя остановками с динамическим радиусом
        segment_coords = find_segment_between_stops(start_stop, end_stop, line_coords[direction])

        # Проверяем расстояние между первой и последней точками сегмента
        if segment_coords and calculate_distance(segment_coords[0], segment_coords[-1]) > MAX_SEGMENT_DISTANCE:
            continue  # Пропускаем сегмент, если он превышает 1 км

        # Структура сегмента: начальная и конечная остановки, координаты сегмента
        segment_info = {
            "нач.": start_stop[1],  # Наименование начальной остановки
            "кон.": end_stop[1],  # Наименование конечной остановки
            "segment_coords": segment_coords  # Координаты сегмента
        }

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": start_stop[0]
            },
            "properties": {
                "name": start_stop[1],
                "direction": direction,
                "route": route_name,
                "segment_info": segment_info  # Добавляем данные сегмента в свойства точки
            }
        }
        points_features.append(feature)

        # Обработка конечной остановки
        if i == len(points_list) - 2:
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": end_stop[0]
                },
                "properties": {
                    "name": end_stop[1],
                    "direction": direction,
                    "route": route_name,
                    "segment_info": segment_info  # Добавляем данные сегмента в свойства точки
                }
            }
            points_features.append(feature)

# 3. Объединение LineString и Points в один GeoJSON файл
geojson_output = {
    "type": "FeatureCollection",
    "features": line_string_features + points_features  # Включаем и LineString, и Points
}

# Сохранение данных в файл GeoJSON
output_file = f'../converter/convert_files/{city_name}_route_{route_name}.geojson'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(geojson_output, f, indent=4)

print(f"Файл {output_file} успешно создан.")
