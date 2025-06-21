import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
import datetime 
import re
import threading

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
}

def parse_page_content(url, keyword_for_db="通用"):
    
    try:
        response = requests.get(url, headers=headers, timeout=10) 
        response.encoding = 'utf-8'

        soup = BeautifulSoup(response.text, 'lxml')

        datadict = {}
        datadict['link'] = url

        title_div = soup.find('div', class_='Artical_Title')
        datadict['title'] = title_div.find('h1').text.strip() if title_div and title_div.find('h1') else "未找到标题"

        source_date_div = soup.find('div', class_='Artical_Share_Source')
        if source_date_div:
            source_span = source_date_div.find('span')
            datadict['source'] = source_span.text.strip() if source_span else "未找到来源"
            
            date_span = soup.find('span', class_='Artical_Share_Date')
            raw_date_str = date_span.text.strip() if date_span else datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            try:
                match = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', raw_date_str)
                if match:
                    matched_str = match.group(0) 
                    parsed_date = datetime.datetime.strptime(matched_str, '%Y-%m-%d %H:%M')
                    datadict['time'] = parsed_date.strftime('%Y-%m-%d %H:%M:%S')
                    datadict['publishTime'] = parsed_date.strftime('%Y-%m-%d')
                else:
                    try:
                        parsed_date = datetime.datetime.strptime(raw_date_str, '%Y-%m-%d %H:%M:%S')
                        datadict['time'] = raw_date_str
                        datadict['publishTime'] = parsed_date.strftime('%Y-%m-%d')
                    except ValueError:
                        now = datetime.datetime.now()
                        datadict['time'] = now.strftime('%Y-%m-%d %H:%M:%S')
                        datadict['publishTime'] = now.strftime('%Y-%m-%d')
            except Exception as e:
                print(f"日期解析失败 for '{raw_date_str}': {e}. Using current time.")
                now = datetime.datetime.now()
                datadict['time'] = now.strftime('%Y-%m-%d %H:%M:%S')
                datadict['publishTime'] = now.strftime('%Y-%m-%d')


        content_div = soup.find('div', class_='Artical_Content')
        if content_div:
            paragraphs = content_div.find_all('p')
            content_text = '\n'.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
        else:
            content_text = '未找到内容'
        datadict['content'] = content_text
        datadict['summary'] = content_text[:150] + '...' if len(content_text) > 150 else content_text


        # 提取图片URL
        img_tags = content_div.find_all("img") if content_div else []
        img_urls = []
        for img in img_tags:
            src = img.get("src")
            if src:
                if src.startswith("//"):
                    src = "https:" + src 
                img_urls.append(src)
        datadict['image'] = img_urls[0] if img_urls else 'https://placehold.co/400x250/CCCCCC/000000?text=无图'
        datadict['image_desc'] = datadict['title'] + "相关图片" 

        datadict['domain'] = url.split('/')[2] 
        datadict['company'] = datadict['source'] 
        datadict['contact'] = f"contact@{datadict['domain']}"
        datadict['keyword'] = keyword_for_db if keyword_for_db is not None else "通用" # 默认关键字，实际应从搜索关键词或文本分析获取
        datadict['visit_count'] = 0 
        if datadict['title'] in ["未找到标题", ""] or datadict['content'] in ["未找到内容", ""]:
            pass
        else: 
            return datadict
    except Exception as e:
        print(f"解析页面失败 {url}: {e}")
        return None

def crawl_news_from_chinadaily(query_keyword, page_count=1):
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage') 
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options) 

    all_news_data = []

    try:
        start_url = f"https://newssearch.chinadaily.com.cn/cn/search?query={query_keyword}"
        driver.get(start_url)
        time.sleep(3) 

        for page in range(1, page_count + 1):
            print(f"正在处理第 {page} 页，关键词：{query_keyword}")

            if page > 1:
                js_code = f"$SearchController.pagging({page})"
                driver.execute_script(js_code)
                time.sleep(2) 

            soup = BeautifulSoup(driver.page_source, "html.parser")
            articles = soup.find_all("div", class_="art_detail")
            
            current_page_urls = []
            for art in articles:
                a_tag = art.find("a", class_="art_pic")
                if a_tag and a_tag.get("href"):
                    current_page_urls.append(a_tag["href"])
            
            for url in current_page_urls:
                news_item = parse_page_content(url, query_keyword)
                if news_item:
                    all_news_data.append(news_item)
                time.sleep(0.5) 

    except Exception as e:
        print(f"爬取过程出现错误: {e}")
    finally:
        driver.quit() 

    print(f"\n共爬取到 {len(all_news_data)} 条新闻数据。")
    return all_news_data

if __name__ == '__main__':
    test_keyword = "中美关系"
    crawled_results = crawl_news_from_chinadaily(test_keyword, page_count=5)
    for i, news in enumerate(crawled_results):
        print(f"--- 新闻 {i+1} ---")
        print(f"标题: {news.get('title')}")
        print(f"来源: {news.get('source')}")
        print(f"发布时间: {news.get('time')}")
        print(f"链接: {news.get('link')}")
        print(f"图片: {news.get('image')}")
        print(f"摘要: {news.get('summary')}")
        print("-" * 20)
