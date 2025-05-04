import os, time, re, asyncio
from io import BytesIO
from datetime import datetime

from settings import *

from openai import OpenAI
from bs4 import BeautifulSoup
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from aiogram import Bot, Dispatcher, types #v.aiogram 2.25.2
from aiogram.types import InputFile
from aiogram.utils import executor
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class LinkStates(StatesGroup):
    waiting_for_link = State()

#Получаем отредактированный текст статьи через ChatGPT
def getText(urlOnArticle):
	
	client = OpenAI(
		api_key = KEY_OPENAI,
		base_url = URL_REPEATER
	)

	response = client.responses.create(
		model="gpt-4o",
		tools=[{
			"type": "web_search_preview",
			"search_context_size": "low",
			"user_location": {
				"type": "approximate",
				"country": "RU",
				"city": "Moscow",
				"region": "Moscow"
				}
			}],
		input=f'{urlOnArticle} {request_for_ai}'
	)

	return response.output[1].content[0].text

#Получаем изображение статьи
def getImages(urlOnArticle):
	
    response = requests.get(urlOnArticle)
    soup = BeautifulSoup(response.text, 'html.parser')

    photo_div = soup.find('div', class_='photoview__open')
    if photo_div:
        img = photo_div.find('img')

        if img:
            if not os.path.exists('downloaded_images'):
                os.makedirs('downloaded_images')

            # for img in images:
            img_url = img.get('src')  # Берём ссылку из атрибута src
            parts = img_url.split("/")
            response_img = requests.get(img_url, headers=headers)
            image_data = BytesIO(response_img.content)
            namefile = str(parts[len(parts)-1]).replace(":", "_")
            with open(f"downloaded_images/{namefile}", 'wb') as f:
                f.write(image_data.read())
            return f"downloaded_images/{namefile}"
        else: 
            return False
    else: 
        return False

#Получаем видео статьи
def getVideos(urlOnArticle):
    # Настройка Selenium
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Запуск в фоновом режиме (без GUI)
    driver = webdriver.Chrome(options=chrome_options)

    try:
        driver.get(urlOnArticle)

        # Ждем, пока появится хотя бы один элемент <video class="vjs-tech">
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "video.vjs-tech"))
        )

        # Дополнительная задержка для полной загрузки (если требуется)
        time.sleep(2)

        # Получаем HTML-код страницы
        page_source = driver.page_source

        # Парсим с BeautifulSoup
        soup = BeautifulSoup(page_source, "html.parser")

        videos = soup.find_all("video", class_="vjs-tech")
        
        if not os.path.exists('downloaded_videos'):
            os.makedirs('downloaded_videos')
            
        for video in videos:
            video_url = video.get('src')
            parts = video_url.split("/")
            response_video = requests.get(video_url, headers=headers)
            video_data = BytesIO(response_video.content)
            namefile = str(parts[len(parts)-1]).replace(":", "_")
            with open(f"downloaded_videos/{namefile}", 'wb') as f:
                f.write(video_data.read())
            return f"downloaded_videos/{namefile}"

    except Exception as e:
        return False

    finally:
        driver.quit()

#Получаем статьи
async def getArticles(urlOnSection):

    response = requests.get(urlOnSection)
    soup = BeautifulSoup(response.text, 'html.parser')

    # Шаг 1: найти главный div
    main_div = soup.find('div', class_='list list-tags', attrs={'data-view': 'tags'})

    if main_div:
        # Шаг 2: найти все статьи
        items = main_div.find_all('div', class_='list-item', attrs={'data-type': 'article'})
        
        for item in items:

            if checkAmountPosts() == False:
                print(f'{getCurrentTime()} Размещение не выполнено. Достигнут лимит постов в день')
                break

            link_tag = item.find('a', class_='list-item__title')
            href = link_tag['href'] if link_tag and link_tag.has_attr('href') else None
            if href.strip().startswith('https://rsport.ria.ru/'):
                print(f'{getCurrentTime()} Статья пропущена, ссылка ведет на поддомен rsport.ria.ru')
                continue
            if check_to_history(href):
                continue
            title = link_tag.get_text(strip=True).upper() if link_tag else None

            # Найти <div data-type="date">
            date_tag = item.find('div', class_='list-item__info-item', attrs={'data-type': 'date'})
            time = date_tag.get_text(strip=True) if date_tag else None

            # Найти <div data-type="views"> и извлечь <span>
            views_tag = item.find('div', class_='list-item__info-item', attrs={'data-type': 'views'})
            views_span = views_tag.find('span') if views_tag else None
            views = views_span.get_text(strip=True) if views_span else None


            time_pattern = re.compile(r'^\d{1,2}:\d{2}$')
            # Печать результатов
            if time_pattern.match(time):

                try:
                    text = getText(href)
                    # text = "It's test text"
                except:
                    print(f"{getCurrentTime()} AI не смог отредактировать текст, возможно закончильсь деньги")
                    break
                # text = "Это тестовый текст"
                if text == "Не найдено." or text == "Не найдено":
                    print(f'{getCurrentTime()} AI не смог найти статью или обработать полученый текст')
                    continue 
                if len(text) > 1023:
                    print(f'{getCurrentTime()} Статья пропущена, длина текста ({len(text)}) выше допустимого значения')
                    print(text)
                    continue

                media = getImages(href)
                if media == False:
                     media = getVideos(href)
                
                await placePost(media, title, text, time, views)
                print(f'{getCurrentTime()} Пост "{title}" успешно размещен')
                add_to_history(href)
                addAmountPosts()
                if media != False:
                    deleteMedia(media)
                # await asyncio.sleep(DELAY_POST)
                break
        print(f"{getCurrentTime()} Все доступные статьи опубликованы")
    else:
        print("Главный массив со статьями не найден на странице")

#Публикуем пост в телеграм
async def placePost(media, title, text, time, views):
    # text = f"<b>{title}</b>\n\n{text}"

    if media.strip().startswith('downloaded_images'):
        photo = InputFile(media)
        await bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=text, parse_mode="html")
    elif media.strip().startswith('downloaded_videos'):
        video = InputFile(media)
        await bot.send_video(chat_id=CHANNEL_ID, video=video, caption=text, parse_mode="html")
    else:
        await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="html")

#Добавляем ссылку в историю
def add_to_history(line: str) -> None:
    try:
        with open("history.txt", "a", encoding="utf-8") as file:
            file.write(line + "\n")  # Добавляем строку с переносом на новую строку
    except Exception as e:
        print(f"Ошибка при записи в файл: {e}")

#Проверяем историю
def check_to_history(search_str):
    try:
        with open("history.txt", 'r', encoding='utf-8') as file:
            for line in file:
                if search_str in line:
                    return True
        return False
    except FileNotFoundError:
        return False
    except Exception as e:
        print(f"Произошла ошибка: {str(e)}")
        return False

#Удаляем файл после публикации поста
def deleteMedia(file_path):
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        else:
            print(f"Файл {file_path} не существует")
    except Exception as e:
        print(f"Ошибка при удалении файла {file_path}: {str(e)}")

#Получаем текущее дату и время
def getCurrentTime():
    current_time = datetime.now()
    formatted_time = current_time.strftime("%d.%m.%y %H:%M |")
    return formatted_time

#Проверяем количество постов за текущий день
def checkAmountPosts():

    amount = "0"
    filename = "posts.txt"

    if not os.path.exists(filename):
        with open(filename, "w") as file:
            file.write(amount)
    with open(filename, "r") as file:
        amount = file.read()
    if amount == LIMIT_POSTS_IN_DAY:
        return False
    return True

#Добавляем +1 к количеству лимита по постам
def addAmountPosts():
    amount = "0"
    filename = "posts.txt"

    with open(filename, "r") as file:
        amount = file.read()

    with open(filename, "w") as file:
        file.write(str(int(amount) + 1))

#Проверяем время на выполнение обнуления лимитов по постам
def updateLimits():
    now = datetime.now()
    time1 = now.strftime("%Y-%m-%d %H:%M")
    datenow = now.strftime("%Y-%m-%d")
    time2 = f"{datenow} 23:00"
    
    # Преобразуем строки времени в объекты datetime
    t1 = datetime.strptime(time1, "%Y-%m-%d %H:%M")
    t2 = datetime.strptime(time2, "%Y-%m-%d %H:%M")

    if t1 > t2:
        filename = "posts.txt"
        if os.path.exists(filename):
            os.remove(filename)

#Проверяем резрешено ли в это время публиковать посты
def timePosting():
    now = datetime.now()
    datenow = now.strftime("%Y-%m-%d")
    postingFrom = f"{datenow} {POSTING_FROM}"
    postingBefor = f"{datenow} {POSTING_BEFOR}"

    postingFromObject = datetime.strptime(postingFrom, "%Y-%m-%d %H:%M")
    postingBeforObject = datetime.strptime(postingBefor, "%Y-%m-%d %H:%M")

    if now > postingFromObject and now < postingBeforObject:
        return True
    print(f"{getCurrentTime()} В это время постинг ограничен настройками")
    return False

#Добавляем пост по ссылке отправленной боту
async def addPostOnLink(link):
    try:
        text = getText(link)
    except:
        print(f"{getCurrentTime()} AI не смог отредактировать текст, возможно закончильсь деньги")
        return

    media = getImages(link)
    if media == False:
            media = getVideos(link)

    if media.strip().startswith('downloaded_images'):
        photo = InputFile(media)
        await bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=text, parse_mode="html")
    elif media.strip().startswith('downloaded_videos'):
        video = InputFile(media)
        await bot.send_video(chat_id=CHANNEL_ID, video=video, caption=text, parse_mode="html")
    else:
        await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="html")
    add_to_history(link)
    deleteMedia(media)
    
#Обрабатываем команду /postlink
@dp.message_handler(Command("postlink"))
async def cmd_postlink(message: types.Message):
    if message.from_user.username == 'endrfn866':	
	await message.answer("Пожалуйста, отправьте ссылку.")
	await LinkStates.waiting_for_link.set()
    else:
	await message.answer("⚠️ Функция доступна только для администации")

#Создаем пост на основе отправленной боту ссылки
@dp.message_handler(state=LinkStates.waiting_for_link)
async def process_link(message: types.Message, state: FSMContext):
    link = message.text
    if link.startswith(('http://ria.ru', 'https://ria.ru')):
        if check_to_history(link):
            await message.answer(f'Такой пост уже есть "{link}"')
            return
        await addPostOnLink(link)
        await message.answer(f'Пост на основе ссылки "{link}" размещен')
        await state.finish()
    else:
        await message.answer("Это не похоже на ссылку. Пожалуйста, отправьте действительную ссылку.")
        await state.finish()

#Запускае основную работу бота
async def start_posting():
    while True:
        updateLimits()
        if timePosting():
            await getArticles(URL_SECTION)
        print(f"{getCurrentTime()} Следующая проверка через {CHECK_TIME / 60} мин.")
        await asyncio.sleep(CHECK_TIME) #Проверяем свежие статьи каждый час

#Запускаем основную функцию
async def main(_):
    #asyncio.create_task(start_posting())
    print(f"{getCurrentTime()} Бот запущен")   

if __name__ == "__main__":
	executor.start_polling(dp, skip_updates=True, on_startup=main)

