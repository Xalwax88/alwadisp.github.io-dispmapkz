from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import json
import re
from geopy.distance import geodesic
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Секретный ключ для сессий

# Инициализация LoginManager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Переадресация на страницу логина

# Пример списка пользователей (можно заменить на реальную базу данных)
users = {
    "admin": {"password": "adminpass"},
    "user": {"password": "userpass"},
    "alwa": {"password": "ml500amg"}
}


# Модель пользователя
class User(UserMixin):
    def __init__(self, username):
        self.id = username


# Функция для загрузки пользователя
@login_manager.user_loader
def load_user(username):
    if username in users:
        return User(username)
    return None


# Функция для расчета расстояния между двумя точками
def calculate_distance(coord1, coord2):
    return geodesic(coord1, coord2).meters


# Функция для парсинга данных и создания GeoJSON
def parse_and_convert_to_geojson(city_name, route_name, file_content):
    line_string_pattern = re.compile(r'type:\s*"LineString",\s*coordinates:\s*\[(.*?)\]\s*}', re.DOTALL)
    line_strings = line_string_pattern.findall(file_content)

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
                    "direction": i,
                    "type": 0,
                    "segment_info": ''
                }
            }
            line_string_features.append(feature)

    point_pattern = re.compile(r'coordinates:\s*\[(\d+\.\d+),\s*(\d+\.\d+)\].*?hintContent:\s*\'(.*?)\'', re.DOTALL)
    points = point_pattern.findall(file_content)

    points_features = []
    hint_counter = {}
    points_by_direction = {0: [], 1: []}

    for point in points:
        coord = [float(point[1]), float(point[0])]
        hint_content = point[2]

        if hint_content in hint_counter:
            hint_counter[hint_content] += 1
        else:
            hint_counter[hint_content] = 0

        current_direction = hint_counter[hint_content] % 2
        points_by_direction[current_direction].append((coord, hint_content, current_direction))

    def find_segment_between_stops(start_point, end_point, line_coords):
        start_coord = start_point[0]
        end_coord = end_point[0]
        segment_coords = []

        start_index = None
        end_index = None
        radius = 300

        while start_index is None or end_index is None:
            for i, coord in enumerate(line_coords):
                if start_index is None and calculate_distance(coord, start_coord) <= radius:
                    start_index = i
                if end_index is None and calculate_distance(coord, end_coord) <= radius:
                    end_index = i
            radius += 100
            if radius > 1500:
                break

        if start_index is not None and end_index is not None and start_index < end_index:
            segment_coords = line_coords[start_index:end_index + 1]
        return segment_coords

    MAX_SEGMENT_DISTANCE = 1500

    for direction, points_list in points_by_direction.items():
        for i in range(len(points_list) - 1):
            start_stop = points_list[i]
            end_stop = points_list[i + 1]
            if start_stop[2] != end_stop[2]:
                continue
            segment_coords = find_segment_between_stops(start_stop, end_stop, line_coords[direction])
            if segment_coords and calculate_distance(segment_coords[0], segment_coords[-1]) > MAX_SEGMENT_DISTANCE:
                continue

            segment_info = {
                "нач.": start_stop[1],
                "кон.": end_stop[1],
                "segment_coords": segment_coords
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
                    "segment_info": segment_info
                }
            }
            points_features.append(feature)

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
                        "segment_info": segment_info
                    }
                }
                points_features.append(feature)

    geojson_output = {
        "type": "FeatureCollection",
        "features": line_string_features + points_features
    }

    return geojson_output


# Маршрут для логина
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']

        if username in users and users[username]['password'] == password:
            user = User(username)
            login_user(user)
            flash('Успешный вход!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неправильный логин или пароль.', 'danger')

    return render_template('login.html')


# Маршрут для выхода
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('login'))


# Основной маршрут с авторизацией
@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        city_name = request.form['city_name']
        route_name = request.form['route_name']
        file_content = request.form['file_content']

        geojson_data = parse_and_convert_to_geojson(city_name, route_name, file_content)

        return jsonify(geojson_data)

    return render_template('index.html')


if __name__ == "__main__":
    app.run(debug=True)
