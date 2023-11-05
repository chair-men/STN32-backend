import json
from flask import Flask, request
from flask_cors import CORS
import sqlite3
from config import SQLITE_DATABASE, DATABASE_URI
import pandas as pd
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from langchain.chains import LLMMathChain
from langchain.llms import OpenAI
from langchain.utilities import SQLDatabase
from langchain_experimental.sql import SQLDatabaseChain
from langchain.agents import initialize_agent, Tool
from langchain.agents import AgentType
from llm_helper import greeting_tool, explanation_tool

load_dotenv()
llm = OpenAI(temperature=0.1, openai_api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
CORS(app)

@app.route("/")
def base_route():
    return "Server is running", 200

@app.route("/retrieve_locations")
def retrieve_locations():
    try:
        conn = sqlite3.connect(SQLITE_DATABASE)
        cursor = conn.cursor()

        days_before = int(request.args.get("before"))
        date = datetime(2023, 10, 29 - days_before, 0, 0, 0).strftime("%Y-%m-%d")
        query = f'SELECT * FROM locations WHERE timestamp LIKE "{date + "%"}";'

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
            result = df.groupby('interval', observed=False).size().reset_index(name='count')

            filtered_df = result[result['interval'].apply(lambda x: x.left.date() == pd.Timestamp(date).date())]
            formatted_result = [(str(intv.left.hour).zfill(2) + ":00", cnt) for intv, cnt in zip(filtered_df['interval'], filtered_df['count'])]
            sorted_results[section] = formatted_result

        json_data = json.dumps(sorted_results, indent=4)

        conn.close()
        return json_data, 200
    except Exception as e:
        print(e)
        return f"Something went wrong when retrieving records: {e}", 500

@app.route("/retrieve_sections")
def retrieve_sections():
    try:
        conn = sqlite3.connect(SQLITE_DATABASE)
        cursor = conn.cursor()

        query = "SELECT * FROM sections;"
        cursor.execute(query)
        rows = cursor.fetchall()

        column_names = [description[0] for description in cursor.description]
        dict_rows = [dict(zip(column_names, row)) for row in rows]

        formatted_data = [
            {
                "geometry": { 
                    "x": row["x"],
                    "y": row["y"],
                    "width": row["width"],
                    "height": row["height"],
                    "type": "RECTANGLE"
                },
                "data": {
                    "id": row['id'], 
                    "text": row["text"],
                }
            }
            for row in dict_rows
        ]

        json_data = json.dumps(formatted_data, indent=4)

        conn.close()
        return json_data, 200

    except Exception as e:
        print(e)
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

        cursor.execute(f"DELETE FROM sections;")

        for new_section in new_sections:
            section_name = str(new_section['text'])
            x = float(new_section['x'])
            y = float(new_section['y'])
            width = float(new_section['width'])
            height = float(new_section['height'])

            x_min = x / 100 * img_width
            x_max = x_min + img_width * width / 100
            y_min = y / 100 * img_height
            y_max = y_min + img_height * height / 100

            print(x_min, x_max, y_min, y_max)

            cursor.execute(f"""
                UPDATE locations 
                SET section = '{section_name}'
                WHERE (x_pos BETWEEN {x_min} AND {x_max})
                AND (y_pos BETWEEN {y_min} AND {y_max});""")
            
            cursor.execute(f"""
                INSERT INTO sections (x, y, width, height, text)
                VALUES({x}, {y}, {width}, {height}, '{section_name}');""")
            
        conn.commit()
        conn.close()

        return "Successfully updated sections", 200
    except Exception as e:
        print(e)
        return f"Something went wrong when updating section: {e}", 500

@app.route("/query_llm", methods=["POST"])
def query_llm():
    data = request.json
    user_query = data['query']

    llm_math_chain = LLMMathChain.from_llm(llm=llm)

    db = SQLDatabase.from_uri(DATABASE_URI)
    db_chain = SQLDatabaseChain.from_llm(db=db, llm=llm)

    tools = [
        Tool(
            name="Greeting", 
            func=greeting_tool,
            description="Responds to common greetings",
        ),
        Tool(
            name="Introduction", 
            func=explanation_tool,
            description="Responds to queries on the agent's usage",
        ),
        Tool(
            name="Calculator",
            func=llm_math_chain.run,
            description="useful for when you need to answer questions about math",
        ),
        Tool(
            name="SQLQuery",
            func=db_chain.run,
            description="""useful for when you need to answer questions about traffic in a certain area that is under surveillance. 
            Input should be in the form of a question containing full context. The values in person_id indicates a unique person. 
            The person_id may appear more than once, in a different x_pos and y_pos to show their coordinates. 
            Counting the person_id column would mean to count the number of appearances of people, NOT the number of unique people. 
            The area that is under surveillance can be partitioned into different sectors, as specified in the sections column. 
            Any dates should be formatted as YYYY-MM-DD HH:MM:SS. For example, 20 January 22 should be a range from 2022-01-22 00:00:00 to 2022-01-22 23:59:59. 
            When responding to questions on how many people/person, format your response with 'appearance of people/person' rather than just 'people/person|'.
            """,
        ),
    ]

    chatVM = initialize_agent(tools, llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION)
    response = chatVM.run(user_query)

    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)