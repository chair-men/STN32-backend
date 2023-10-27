import json
from flask import Flask, request
from flask_cors import CORS
import sqlite3
from config import SQLITE_DATABASE
import pandas as pd


app = Flask(__name__)
CORS(app)

@app.route("/")
def base_route():
    return "Server is running", 200

@app.route("/retrieve")
def retrieve_records():
    try:
        conn = sqlite3.connect(SQLITE_DATABASE)
        cursor = conn.cursor()

        query = "SELECT * FROM locations;"
        cursor.execute(query)
        rows = cursor.fetchall()

        column_names = [description[0] for description in cursor.description]
        dict_rows = [dict(zip(column_names, row)) for row in rows]

        sorted_results = {}
        for row in dict_rows:
            if row['section'] in sorted_results:
                sorted_results[row['section']].append(row['timestamp'])
            else:
                sorted_results[row['section']] = [row['timestamp']]

        for section in sorted_results:
            timestamps = sorted_results[section]
            df = pd.DataFrame({
                'timestamps': pd.to_datetime(timestamps)
            })
            bin_intervals = pd.date_range(start=df['timestamps'].min().floor('2H'), end=df['timestamps'].max().ceil('2H'), freq='2H')
            df['interval'] = pd.cut(df['timestamps'], bins=bin_intervals, right=False, include_lowest=True)
            result = df.groupby('interval').size().reset_index(name='count')

            filtered_df = result[result['interval'].apply(lambda x: x.left.date() == pd.Timestamp('2023-10-27').date())]
            formatted_result = [(str(intv.left.hour).zfill(2) + ":00", cnt) for intv, cnt in zip(filtered_df['interval'], filtered_df['count'])]
            sorted_results[section] = formatted_result

        json_data = json.dumps(sorted_results, indent=4)

        conn.close()
        return json_data, 200
    except Exception as e:
        return f"Something went wrong when retrieving records: {e}", 500

@app.route("/update", methods=['POST'])
def update_sections():
    try:
        data = request.json
        image_data = data['image_dims']
        new_sections = data['sections']

        # Get dimensions of image
        img_width = int(image_data['width'])
        img_height = int(image_data['height'])

        conn = sqlite3.connect(SQLITE_DATABASE)
        cursor = conn.cursor()

        # Reset section column
        cursor.execute(f"UPDATE locations SET section = 'Others';")

        for new_section in new_sections:
            section_name = str(new_section['text'])
            x_min = float(new_section['x']) / 100 * img_width
            x_max = x_min + img_width * int(new_section['width']) / 100
            y_min = float(new_section['y']) / 100 * img_height
            y_max = y_min + img_height * int(new_section['height']) / 100

            print(x_min, x_max, y_min, y_max)

            cursor.execute(f"""
                UPDATE locations 
                SET section = '{section_name}'
                WHERE (x_pos BETWEEN {x_min} AND {x_max})
                AND (y_pos BETWEEN {y_min} AND {y_max});""")
            
        conn.commit()
        conn.close()

        return "Successfully updated sections", 200
    except Exception as e:
        return f"Something went wrong when updating section: {e}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)