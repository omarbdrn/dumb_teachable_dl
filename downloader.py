import requests, m3u8, json, os, ffmpeg
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
import argparse

class Teachable:
    def __init__(self, subdomain, course_id: int, cookies):
        self.subdomain = subdomain
        self.course_id = course_id
        self.cookies = cookies
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Cookie": self.cookies,
            "Referer": "https://player.hotmart.com/"
        }
        self.lectures = []
    
    def get_lectures(self):
        self.headers["Referer"] = f"https://{self.subdomain}.teachable.com/courses/enrolled/{str(self.course_id)}"
        endpoint = f"https://{self.subdomain}.teachable.com/services/layabout/courses/{str(self.course_id)}"
        lectures = []

        try:
            request = requests.get(endpoint, headers=self.headers)
            body = request.json()
            for syllabus in body["syllabus"]:
                lectures.extend(syllabus["lectures"])
        except Exception as e:
            print(f"[get_lectures] {e}")

        self.lectures = lectures
            
        return lectures
    
    def parse_lecture_html(self, lecture_url):
        request = requests.get(lecture_url, headers=self.headers)
        soup = BeautifulSoup(request.content, "html.parser")
        div = soup.find("div", class_="hotmart_video_player")
        attachment_id = int(div.get('data-attachment-id'))
        self.download_attachment(attachment_id)

    def download_lecture(self, lecture_url):
        folder_manager = FolderManager()
        lecture_id = lecture_url.split("/")[-1]
        if folder_manager.folder_exists(str(lecture_id)) == False:
            folder_manager.create_folder(str(lecture_id))

        folder_manager.change_directory(str(lecture_id))
        self.parse_lecture_html(lecture_url)
        folder_manager.go_back()
    
    def download_lectures(self):
        folder_manager = FolderManager()
        if self.lectures == []:
            self.get_lectures()
        
        for lecture in self.lectures:
            lecture_name = lecture["name"]
            lecture_url = f"https://{self.subdomain}.teachable.com{lecture['url']}"
            type = lecture["type"]
            if type != "video":
                continue
            
            if folder_manager.folder_exists(str(lecture_name)) == False:
                folder_manager.create_folder(str(lecture_name))

            folder_manager.change_directory(str(lecture_name))
            self.parse_lecture_html(lecture_url)
            folder_manager.go_back()
            
            break

    def download_attachment(self, attachment_id):
        print("[+] Downloading Attachment, it'll take some time please wait")
        self.headers["Referer"] = f"https://player.hotmart.com/"

        folder_manager = FolderManager()
        if folder_manager.folder_exists(str(attachment_id)) == False:
            folder_manager.create_folder(str(attachment_id))
        
        folder_manager.change_directory(str(attachment_id))    
        endpoint = f"https://{self.subdomain}.teachable.com/api/v2/hotmart/private_video?attachment_id={str(attachment_id)}"
        try:
            request = requests.get(endpoint, headers=self.headers)
            body = request.json()
            url = f"https://player.hotmart.com/embed/{body['video_id']}?signature={body['signature']}&token={body['teachable_application_key']}"
            request = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
            soup = BeautifulSoup(request.content, "html.parser")
            scripts = soup.find(id="__NEXT_DATA__")
            next_data_jsonified = json.loads(scripts.text)
            master_m3u8_url = next_data_jsonified["props"]["pageProps"]["applicationData"]["mediaAssets"][0]["urlEncrypted"]
            downloader = M3U8Segments(master_m3u8_url, attachment_id)
            downloader.download_file()
            folder_manager.go_back()
        except Exception as e:
            print(f"[download_attachment] {e}")
        
        return

class AESKey:
    def __init__(self, key, iv):
        self.key = key
        self.iv = iv

class M3U8Segments:
    def __init__(self, master_url, attachment_id):
        self.master_url = master_url
        self.attachment_id = attachment_id
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", "Referer": "https://player.hotmart.com/"}

    def WriteKey(self, key):
        folder_manager = FolderManager()
        if folder_manager.folder_exists("keys") == False:
            folder_manager.create_folder("keys")

        key_path = "keys/key.bin"
        iv_path = "keys/iv.bin"
        with open(key_path, 'wb') as k:
            k.write(key.key)
        with open(iv_path, 'w') as i:
            i.write(key.iv)
    
    def download_file(self):
        local_filename = f'{str(self.attachment_id)}.ts'
        r = requests.get(self.master_url, headers=self.headers)
        m3u8_master = m3u8.loads(r.text)
        playlist_url = m3u8_master.data['playlists'][-1]['uri']
        
        # Getting Full URL
        full_url = self.master_url.split('/')
        full_url = "/".join(full_url[0:-2])
        full_url += '/'
        quality = playlist_url.split("/")[0] # Video Quality like 1080-720
        playlist_url = f"{full_url}hls/{playlist_url}" # Playlist URL


        new_r = requests.get(playlist_url, headers=self.headers)
        playlist = m3u8.loads(new_r.text)

        # Grabbing Decryption Key
        key_uri = f"{full_url}hls/{quality}/{playlist.keys[0].uri}"
        key_request = requests.get(key_uri, headers=self.headers)
        key = AESKey(key_request.content, playlist.keys[0].iv)
        self.WriteKey(key)

        with open(local_filename, 'wb') as f:
            for segment in playlist.data['segments']:
                url = f"{full_url}hls/{quality}/{segment['uri']}"
                req = requests.get(url, headers=self.headers)
                f.write(req.content)

        decryptor = Decrypt()
        decryptor.ProcessFile(local_filename)

class Decrypt:
    def __init__(self):
        pass

    def DecryptFile(self, file_path):
        key = None
        iv = None
        decrypted = None
        parent_directory = os.path.dirname(file_path)

        key_path = os.path.join(parent_directory, 'keys', 'key.bin')
        iv_path = os.path.join(parent_directory, 'keys', 'iv.bin')

        with open(key_path, 'rb') as k:
            key = k.read()    
        with open(iv_path, 'r') as i:
            iv =bytes(bytearray.fromhex(i.read()[2::]))

        aes = AES.new(key, AES.MODE_CBC, iv)

        with open(file_path, 'rb') as d:
            decrypted = aes.decrypt(d.read())
        return decrypted

    def ProcessFile(self, file_path):
        decrypted = self.DecryptFile(file_path)

        with open(file_path.replace(".ts", "_decrypted.ts"), 'ab') as o:
            o.write(decrypted)

        mp4_converter = MP4Convert(file_path)
        mp4_converter.convert()

class FolderManager:
    def __init__(self):
        self.root = os.getcwd()

    def go_back(self):
        parent_directory = os.path.abspath(os.path.join(self.root, os.pardir))
        if os.path.exists(parent_directory) and os.path.isdir(parent_directory):
            os.chdir(parent_directory)
            self.root = os.getcwd()
            return True
        else:
            return False
        
    def folder_exists(self, folder_name):
        folder_path = os.path.join(self.root, folder_name)
        return os.path.exists(folder_path) and os.path.isdir(folder_path)

    def get_current_path(self):
        return os.getcwd()

    def create_folder(self, folder_name):
        folder_path = os.path.join(self.root, folder_name)
        os.makedirs(folder_path, exist_ok=True)
        return folder_path

    def change_directory(self, folder_name):
        folder_path = os.path.join(self.root, folder_name)
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            os.chdir(folder_path)
            self.root = os.getcwd()
            return True
        else:
            return False

class MP4Convert:
    def __init__(self, filepath):
        self.file_path = filepath
    
    def convert(self):
        (
            ffmpeg.input(self.file_path.replace(".ts", "_decrypted.ts"))
            .output(self.file_path.replace(".ts", ".mp4"))
            .run()
        )

folder_manager = FolderManager()
if folder_manager.folder_exists("lectures") == False:
    folder_manager.create_folder("lectures")
folder_manager.change_directory("lectures")

course_id = 0
teachable_sample = Teachable("subdomain", int(course_id), "Cookies")
parser = argparse.ArgumentParser(description='Teachable Testing') # This script is garbage but it does the job.
parser.add_argument('--all', action='store_true')
parser.add_argument('--single', action='store_true')
parser.add_argument('-u', '--url', help='Url of Lecture', required=False)
args = parser.parse_args()

if args.all:
    teachable_sample.download_lectures()
elif args.single:
    lecture_url = args.url # Check if the url has /courses/ in it as validation
    teachable_sample.download_lecture(lecture_url)
