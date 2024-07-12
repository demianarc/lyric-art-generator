import os
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import openai

load_dotenv()

app = Flask(__name__)

GENIUS_API_TOKEN = os.getenv('GENIUS_ACCESS_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

openai.api_key = OPENAI_API_KEY

headers = {
    'Authorization': f'Bearer {GENIUS_API_TOKEN}'
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search_song', methods=['GET'])
def search_song():
    query = request.args.get('query')
    search_url = f'https://api.genius.com/search?q={query}'
    response = requests.get(search_url, headers=headers)
    json_response = response.json()

    if 'response' in json_response and 'hits' in json_response['response']:
        hits = json_response['response']['hits']
        songs = [{'title': hit['result']['title'], 'id': hit['result']['id'], 'artist': hit['result']['primary_artist']['name']} for hit in hits]
        return jsonify(songs)
    else:
        return jsonify([])

def preprocess_with_gpt4o(lyrics, song_info):
    prompt = f"""
    You are an AI assistant tasked with formatting and enhancing song lyrics for image generation. 
    The song details are as follows:
    Title: {song_info['title']}
    Artist: {song_info['artist']}
    Album: {song_info.get('album', 'Unknown')}
    Release Date: {song_info.get('release_date', 'Unknown')}
    
    Here are the raw lyrics:
    {lyrics}

    Please look at these lyrics, removing any unnecessary annotations or metadata or cursewords. 
    Then, provide a brief analysis of the song's themes, mood, and key imagery. 
    Finally, suggest 3-5 vivid visual elements that could be incorporated into an artistic representation of this song.
    
    Format your response as follows:

    Analysis:
    [Your analysis here]

    Visual Elements:
    - [Element 1]
    - [Element 2]
    - [Element 3]
    """

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that formats and analyzes song lyrics."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message['content']

@app.route('/generate_art', methods=['POST'])
def generate_art():
    song_id = request.form['song_id']
    song_url = f'https://api.genius.com/songs/{song_id}'
    response = requests.get(song_url, headers=headers)
    song_info = response.json().get('response', {}).get('song', {})

    if not song_info:
        return 'Song not found', 404

    lyrics_path = song_info['path']
    page_url = f'https://genius.com{lyrics_path}'
    page = requests.get(page_url)
    html = BeautifulSoup(page.text, 'html.parser')
    
    lyrics_container = html.find('div', class_='lyrics')
    if not lyrics_container:
        lyrics_container = html.find('div', class_='Lyrics__Container-sc-1ynbvzw-6')
    if not lyrics_container:
        lyrics_container = html.select_one('div[class^="Lyrics__Container-"]')
    
    if lyrics_container:
        lyrics_text = lyrics_container.get_text(separator='\n').strip()
    else:
        return 'Lyrics not found', 404

    # Preprocess lyrics with GPT-4o
    preprocessed_content = preprocess_with_gpt4o(lyrics_text, {
        'title': song_info['title'],
        'artist': song_info['primary_artist']['name'],
        'album': song_info.get('album', {}).get('name', 'Unknown'),
        'release_date': song_info.get('release_date', 'Unknown')
    })

    # Generate image using DALL-E
    try:
        response = openai.Image.create(
            prompt=f"""Create an incredibly realistic and cinematic photograph inspired by this song analysis and visual elements: {preprocessed_content}. 
            Nothing too cheesy please. The photo should have a beautiful analog and grainy feel, with exceptional quality and focus. As if it as taken with a leica so keep it natural. 
            Capture the mood and themes of the song in a single, powerful image. 
            Consider using interesting lighting, compelling composition, and rich, emotive colors. 
            The image should feel like a still from an award-winning music video or a cover shot for a prestigious music magazine. 
            Do not include any text or recognizable faces. 
            Emphasize texture, depth, and atmosphere to create a visually striking and emotionally resonant photograph.""",
            n=1,
            size="1024x1024",
            model="dall-e-3"
        )
        image_url = response['data'][0]['url']
    except Exception as e:
        print(f"Error generating image: {e}")
        image_url = None

    return render_template('result.html', 
                           lyrics=preprocessed_content, 
                           image_url=image_url, 
                           song_info=song_info)

if __name__ == '__main__':
    app.run(debug=True)