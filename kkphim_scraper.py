import urllib.request
import json
import argparse
import os

def fetch_api(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Scrape KKPhim for IPTV")
    parser.add_argument('-f', '--file', default='kkphim_movies.txt', help='File containing KKPhim movie slugs')
    parser.add_argument('-o', '--output', default='playlist.m3u', help='Output M3U file')
    args = parser.parse_args()

    slugs = []
    if os.path.exists(args.file):
        with open(args.file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Can extract slug from full url if user pasted full url
                    if 'phimapi.com/phim/' in line:
                        slug = line.split('phimapi.com/phim/')[-1].strip('/')
                    elif '/' in line:
                        slug = line.split('/')[-1].strip('/')
                    else:
                        slug = line
                    slugs.append(slug)

    # Optional: fetch 10 latest movies automatically
    latest_data = fetch_api('https://phimapi.com/danh-sach/phim-moi-cap-nhat?page=1')
    if latest_data and 'items' in latest_data:
        for item in latest_data['items'][:10]:
            if item['slug'] not in slugs:
                slugs.append(item['slug'])

    # Write in append mode because yanhh3d_scraper might have run first
    mode = 'a' if os.path.exists(args.output) else 'w'
    with open(args.output, mode, encoding='utf-8') as f:
        if mode == 'w':
            f.write("#EXTM3U\n")

        for slug in slugs:
            print(f"Processing KKPhim movie: {slug}")
            data = fetch_api(f"https://phimapi.com/phim/{slug}")
            if not data or not data.get('status'):
                continue
                
            movie = data['movie']
            title = movie.get('name', 'Unknown')
            genre = movie.get('category', [{'name': 'Khác'}])[0]['name']
            
            episodes = data.get('episodes', [])
            count = 0
            for server in episodes:
                for ep in server.get('server_data', []):
                    m3u8_url = ep.get('link_m3u8')
                    if m3u8_url:
                        ep_name = ep.get('name', '')
                        f.write(f'#EXTINF:-1 group-title="{genre};{title}", Tập {ep_name}\n')
                        f.write(f"{m3u8_url}\n")
                        count += 1
            print(f"Found {count} episodes for {title}")

    print("KKPhim scraper finished!")

if __name__ == "__main__":
    main()
