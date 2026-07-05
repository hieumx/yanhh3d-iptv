import urllib.request
import re
import sys
import time
import argparse
import os
import json
import base64

CACHE_FILE = 'cache.json'
m3u8_cache = {}
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            m3u8_cache = json.load(f)
    except Exception:
        m3u8_cache = {}

def save_cache():
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(m3u8_cache, f, indent=4)
    except Exception as e:
        print(f"Error saving cache: {e}")

def fetch_html(url, referer=None):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    if referer:
        headers['Referer'] = referer
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def fetch_latest_movies(base_url="https://yanhh3d.im", limit=40):
    print(f"Fetching latest movies from homepage {base_url}...")
    html = fetch_html(base_url)
    if not html:
        return []
        
    all_links = re.findall(r'href="(https?://yanhh3d\.[a-z]+/[a-z0-9-]+)"', html)
    bad_keywords = ['the-loai', 'quoc-gia', 'danh-sach', 'nam-phat-hanh', 'login', 'register', 'hoan-thanh', 'hoat-hinh-4k', 'hoat-hinh-2d', 'hoat-hinh-3d', 'dang-chieu', 'phim-le', 'phim-bo', 'ova', 'thuyet-minh', 'vietsub', 'moi-cap-nhat', 'loc-phim']

    movies = []
    seen = set()
    for link in all_links:
        if link in seen:
            continue
        if any(bad in link for bad in bad_keywords):
            continue
        movies.append(link)
        seen.add(link)
        if len(movies) >= limit:
            break
            
    return movies

def extract_movie_info(url):
    html = fetch_html(url)
    if not html:
        return None, "Unknown", "Unknown", []
    
    movie_slug = url.strip('/').split('/')[-1]
    
    # Extract title
    title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
    movie_title = title_match.group(1).strip() if title_match else movie_slug.replace('-', ' ').title()
    
    # Extract genres
    genres = re.findall(r'<a class="name genre" href="[^"]+">([^<]+)</a>', html)
    valid_genres = [g for g in genres if g.lower() not in ['cn animation', 'hhkungfu', 'hoạt hình 3d', 'hoạt hình 2d', 'hoạt hình 4k']]
    primary_genre = valid_genres[0] if valid_genres else (genres[0] if genres else "Khác")
    
    # Base url for domain-agnostic links
    from urllib.parse import urlparse
    domain = f"https://{urlparse(url).netloc}"
    
    # Extract episodes
    ep_links_in_movie = re.findall(rf'href="(https?://[^/]+/[^"]*{movie_slug}/tap-\d+[^"]*)"', html)
    if not ep_links_in_movie:
        ep_links_in_movie = re.findall(rf'href="(/[^"]*{movie_slug}/tap-\d+[^"]*)"', html)
        ep_links_in_movie = [domain + link if link.startswith('/') else link for link in ep_links_in_movie]
    
    if not ep_links_in_movie:
        print(f"Could not find any episode link on {url}")
        return movie_slug, movie_title, primary_genre, []
        
    first_ep_url = ep_links_in_movie[0]
    
    player_html = fetch_html(first_ep_url)
    
    all_eps = set(re.findall(rf'href="(https?://[^/]+/[^"]*{movie_slug}/tap-\d+[^"]*)"', player_html))
    all_eps_relative = set(re.findall(rf'href="(/[^"]*{movie_slug}/tap-\d+[^"]*)"', player_html))
    for ep in all_eps_relative:
         all_eps.add(domain + ep)
    all_eps.add(first_ep_url)
    
    def get_ep_num(link):
        match = re.search(r'tap-(\d+)', link)
        return int(match.group(1)) if match else 0
        
    ep_map = {}
    for ep in all_eps:
        num = get_ep_num(ep)
        if num not in ep_map or "sever" not in ep:
            ep_map[num] = ep
            
    sorted_eps = [ep_map[num] for num in sorted(ep_map.keys())]
    return movie_slug, movie_title, primary_genre, sorted_eps

def get_m3u8_for_episode(ep_url):
    global m3u8_cache
    if ep_url in m3u8_cache:
        cached = m3u8_cache[ep_url]
        if 'streamc.xyz' not in cached and '|' not in cached:
            return cached
        
    html = fetch_html(ep_url)
    if not html:
        return None
        
    sources = re.findall(r'<a[^>]+data-src="([^"]+)"[^>]*>([^<]+)</a>', html)
    
    best_src = None
    best_q = -1
    
    for src, label in sources:
        q_score = 0
        if '4K' in label: q_score = 4
        elif '1080' in label: q_score = 3
        elif 'HD' in label: q_score = 2
        elif 'Link' in label: q_score = 1
        
        if q_score > best_q:
            best_q = q_score
            best_src = src
            
    if not best_src:
        any_m3u8 = re.search(r'https?://[^"\'\s]+\.m3u8[^"\'\s]*', html)
        if any_m3u8:
            m3u8_cache[ep_url] = any_m3u8.group(0)
            return any_m3u8.group(0)
        return None

    # Resolve iframe player HTML
    player_html = fetch_html(best_src, referer=ep_url)
    if not player_html:
        return best_src
        
    if '#EXTM3U' in player_html:
        m3u8_cache[ep_url] = best_src
        return best_src # It is a direct stream
        
    m3u8_match = re.search(r'["\'](https?://[^"\']+\.m3u8(?:\?[^"\']+)?)["\']', player_html)
    if m3u8_match:
        m3u8_url = m3u8_match.group(1)
        m3u8_cache[ep_url] = m3u8_url
        return m3u8_url
        
    obf_match = re.search(r'data-obf="([^"]+)"', player_html)
    if obf_match:
        obf_data = obf_match.group(1)
        try:
            obf_data += "=" * ((4 - len(obf_data) % 4) % 4)
            decoded_str = base64.b64decode(obf_data).decode('utf-8')
            data = json.loads(decoded_str)
            for k in ['pU', 'sU', 'file']:
                if k in data:
                    m3u8_cache[ep_url] = data[k]
                    return data[k]
        except Exception:
            pass
            
    m3u8_cache[ep_url] = best_src
    return best_src

def main():
    parser = argparse.ArgumentParser(description="YanHH3D to IPTV M3U Playlist Generator")
    parser.add_argument('-f', '--file', type=str, default="movies.txt", help="File containing list of movie URLs")
    parser.add_argument('-o', '--output', type=str, default="playlist.m3u", help="Output M3U file")
    
    args = parser.parse_args()
    
    urls = []
    if args.file:
        try:
            with open(args.file, 'r') as f:
                urls.extend([line.strip() for line in f if line.strip() and not line.startswith('#')])
        except Exception as e:
            print(f"Error reading file {args.file}: {e}")
            
    # Auto fetch top 40 movies from homepage
    latest_movies = fetch_latest_movies()
    for m in latest_movies:
        if m not in urls:
            urls.append(m)
            
    if not urls:
        print("No URLs found.")
        return
        
    print(f"Generating M3U playlist for {len(urls)} movies...")
    
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        
        for url in urls:
            print(f"\nProcessing movie: {url}")
            movie_slug, movie_title, primary_genre, ep_links = extract_movie_info(url)
            print(f"Title: {movie_title} | Genre: {primary_genre}".encode('utf-8', 'ignore').decode('utf-8', 'ignore'))
            print(f"Found {len(ep_links)} episodes.")
            
            import concurrent.futures
            
            def process_episode(ep_link):
                ep_num_match = re.search(r'tap-(\d+)', ep_link)
                ep_num = ep_num_match.group(1) if ep_num_match else "Unknown"
                m3u8 = get_m3u8_for_episode(ep_link)
                return ep_num, m3u8
                
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                results = list(executor.map(process_episode, ep_links))
                
                for ep_num, m3u8_url in results:
                    if m3u8_url:
                        # Dùng Tên Phim làm thư mục để gom các tập vào 1 chỗ
                        title = f"Tập {ep_num}"
                        f.write(f'#EXTINF:-1 group-title="{primary_genre};{movie_title}", {title}\n')
                        f.write(f'#EXTVLCOPT:http-referrer=https://yanhh3d.im/\n')
                        f.write(f'#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)\n')
                        
                        if '|' in m3u8_url:
                            m3u8_url = m3u8_url.split('|')[0]
                            
                        f.write(f"{m3u8_url}\n")
                        
    save_cache()
    print(f"\nDone! Playlist saved to {args.output}")

if __name__ == "__main__":
    main()
