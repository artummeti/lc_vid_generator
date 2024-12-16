import os
import json
import requests
import time
from gtts import gTTS
from moviepy.editor import (
    AudioFileClip, 
    concatenate_videoclips,
    ImageClip
)
import tempfile
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import numpy as np

NUM_QUESTIONS = 2  
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
FONT_SIZE = 50
TEXT_COLOR = 'white'
BG_COLOR = (0, 0, 0)
FPS = 24


client = OpenAI()

# get list of problems 
def get_problems_list():
    """
    Fetch list of  problems from LeetCode and return sorted by difficulty
    """

    print("Fetching problems list")
    ALGORITHMS_ENDPOINT_URL = "https://leetcode.com/api/problems/algorithms/"
    resp = requests.get(ALGORITHMS_ENDPOINT_URL)
    if resp.status_code != 200:
        raise Exception("Could not fetch list of problems")

    data = resp.json()
    problems = data["stat_status_pairs"]

    free_problems = []
    for p in problems:
        if not p["paid_only"]:
            title_slug = p["stat"]["question__title_slug"]
            title = p["stat"]["question__title"]
            difficulty = p["difficulty"]["level"]
            frontend_id = p["stat"]["frontend_question_id"]
            free_problems.append((title_slug, difficulty, frontend_id, title))

    # sort by difficulty, then by ID
    free_problems = sorted(free_problems, key=lambda x: (x[1], x[2]))
    print("Problems list fetched and sorted.")
    return free_problems

def get_openai_solution(problem_title, difficulty):
    """
    use gpt-4o to get a solution explanation based on the title and difficulty.
    """
    print(f"creating solution explanation for: {problem_title} (Difficulty: {difficulty})...")
    difficulty_str = {1: "Easy", 2: "Medium", 3: "Hard"}.get(difficulty, "Unknown")

    prompt = f"""
                You are a helpful assistant that provides inferred solutions to coding problems.
                You have  the following info:
                - Title: "{problem_title}"
                - Difficulty: {difficulty_str}

                Based on this, provide a detailed step-by-step solution.
                DO NOT RETURN ANY EXTRA DATA
                """

    response = client.chat.completions.create(
        model='gpt-4o',
        messages=[
            {"role": "system", "content": "You are a helpful assistant providing solutions to coding problems."},
            {"role": "user", "content": prompt}
        ]
    )
    solution = response.choices[0].message.content.strip()
    print("explanation generated")
    return solution

def get_openai_tips(problem_title, difficulty):
    """
    use gpt-4o to get 3 tips based on the title and difficulty.
    """
    print(f"getting tips for: {problem_title} (Difficulty: {difficulty})...")
    difficulty_str = {1: "Easy", 2: "Medium", 3: "Hard"}.get(difficulty, "Unknown")

    prompt = f"""
                You have the following info:
                - Title: "{problem_title}"
                - Difficulty: {difficulty_str}

                Provide 3 concise tips or insights for approaching a problem that fits this title and difficulty.
                Label them as 'Tips:' followed by 3 bullet points.
                """

    response = client.chat.completions.create(
        model='gpt-4o',
        messages=[
            {"role": "system", "content": "You provide short, helpful tips based on the given title and difficulty."},
            {"role": "user", "content": prompt}
        ]
    )
    tips = response.choices[0].message.content.strip()
    print("tips generated.")
    return tips

def text_to_speech(text, filename):
    print(f"converting text to speech : out file: {filename}")
    tts = gTTS(text=text, lang='en')
    tts.save(filename)
    print("tts conversion completed")

def create_text_clip_pillow(text, duration=5, width=1280, height=720, fontsize=50, color='white'):
    # PIL image with a black background
    img = Image.new("RGB", (width, height), color=(0,0,0))
    draw = ImageDraw.Draw(img)

    
    font_path = "arial.ttf"  
    font = ImageFont.truetype(font_path, fontsize)

    #TODO wrap text in video

    text_width, text_height = draw.textsize(text, font=font)
    text_position = ((width - text_width) // 2, (height - text_height) // 2)
    draw.text(text_position, text, font=font, fill=color)

    # PIL image to numpy array
     # then make a ImageClip from the numpy array
    img_np = np.array(img)
    clip = ImageClip(img_np).set_duration(duration)
    return clip

def create_video_for_problem(problem_info, index):
    slug, difficulty, frontend_id, problem_title = problem_info
    print(f"Creating video for problem {index+1}: {problem_title} (Slug: {slug})")

    difficulty_str = {1: "Easy", 2: "Medium", 3: "Hard"}.get(difficulty, "Unknown")
    synthetic_description = f"This is a {difficulty_str} problem titled '{problem_title}'."

    solution_explanation = get_openai_solution(problem_title, difficulty)
    tips_section = get_openai_tips(problem_title, difficulty)

    question_info = f"Problem #{frontend_id}: {problem_title}\n\n{synthetic_description}"
    example_info = f"Example:\n."

    # TODO scrape example of problem

    tips_info = tips_section
    solution_info = f"Solution:\n{solution_explanation}"

    full_narration = f"{question_info}\n\n{example_info}\n\n{tips_info}\n\n{solution_info}"

    audio_temp_file = os.path.join(tempfile.gettempdir(), f"voiceover_{slug}.mp3")
    text_to_speech(full_narration, audio_temp_file)
    print("Loading audio file into moviepy")
    audio_clip = AudioFileClip(audio_temp_file)
    print("audio file loaded.")

    print("Creating video clip")
    segment_durations = [10, 7,7 , 20]
    question_clip = create_text_clip_pillow(question_info, duration=segment_durations[0], width=VIDEO_WIDTH, height=VIDEO_HEIGHT, fontsize=FONT_SIZE)
    example_clip = create_text_clip_pillow(example_info, duration=segment_durations[1], width=VIDEO_WIDTH, height=VIDEO_HEIGHT, fontsize=FONT_SIZE)
    tips_clip = create_text_clip_pillow(tips_info, duration=segment_durations[2], width=VIDEO_WIDTH, height=VIDEO_HEIGHT, fontsize=FONT_SIZE)
    solution_clip = create_text_clip_pillow(solution_info, duration=segment_durations[3], width=VIDEO_WIDTH, height=VIDEO_HEIGHT, fontsize=FONT_SIZE)

    print("Concating video clips")
    final_video = concatenate_videoclips([question_clip, example_clip, tips_clip, solution_clip])

    final_duration = final_video.duration
    audio_duration = audio_clip.duration
    print(f" video duration: {final_duration:.2f}s, audio duration: {audio_duration:.2f}s")

    if audio_duration > final_duration:
        audio_clip = audio_clip.subclip(0, final_duration)

    final_video = final_video.set_audio(audio_clip)

    os.makedirs("created_vids", exist_ok=True)
    output_filename = os.path.join("created_vids", f"problem_{index+1}_{slug}.mp4")
    print(f"Writing final video file: {output_filename}")
    final_video.write_videofile(output_filename, fps=FPS)
    print("Video file created successfully.")

    if os.path.exists(audio_temp_file):
        os.remove(audio_temp_file)
        print(f"Temp audio file removed: {audio_temp_file}")

def main():
    problems = get_problems_list()
    selected_problems = problems[:NUM_QUESTIONS]

    for i, p in enumerate(selected_problems):
        print(f"\nMaking video for problem: {i+1}/{NUM_QUESTIONS}: {p[3]} ({p[0]})")
        try:
            create_video_for_problem(p, i)
        except Exception as e:
            print(f"Error creating video for {p[0]}: {e}")

        # avoid rate limiter
        time.sleep(5)

if __name__ == "__main__":
    main()
