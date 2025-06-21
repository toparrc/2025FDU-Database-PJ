# 服务器（app.py）
from flask import Flask, render_template, request, jsonify, redirect, url_for
import pymysql.cursors
import datetime
import random
import json
import sys
import os
import threading


from pathlib import Path
current_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(current_dir))
from crawler import *


try:
    from crawler import crawl_news_from_chinadaily
except ImportError:
    print("Error: crawler.py not found. Please ensure it's in the same directory or accessible via Python PATH.")
    sys.exit(1)

app = Flask(__name__)
#数据库登录信息
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '********', #MySQL密码
    'db': 'news_db',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

#连接数据库
def get_db_connection():
    try:
        connection = pymysql.connect(**DB_CONFIG)
        return connection
    except Exception as e:
        print(f"数据库连接失败: {e}")
        return None

#把新闻数据整理成前端一条一条的格式
def format_news_for_frontend(db_result):
    if not db_result:
        return []

    formatted_list = []
    results_to_process = [db_result] if isinstance(db_result, dict) else db_result

    for item in results_to_process:
        news_id = item.get('news_id')
        if news_id is None: 
            url_hash = hash(item.get('webpage_url', '')) % (10**7)
            news_id = url_hash
            print(f"Warning: news_id not found in DB result. Using hashed URL as ID: {news_id}")

        #把时间格式转换为标准的格式
        publish_time_obj = item.get('source_time') or item.get('publish_time')
        if isinstance(publish_time_obj, datetime.date) and not isinstance(publish_time_obj, datetime.datetime):
            publish_time_obj = datetime.datetime.combine(publish_time_obj, datetime.time.min)
            
        publish_time_str = publish_time_obj.strftime('%Y-%m-%d') if isinstance(publish_time_obj, datetime.datetime) else str(publish_time_obj).split(' ')[0]

        summary_text = item.get('content') or ""
        summary_text = summary_text[:150] + '...' if len(summary_text) > 150 else summary_text

        formatted_list.append({
            "id": news_id,
            "title": item.get('title', '无标题'),
            "image": item.get('image_url', 'https://placehold.co/400x250/CCCCCC/000000?text=无图'),
            "summary": summary_text,
            "content": item.get('content', '无正文内容'),
            "source": item.get('data_publisher') or item.get('website_domain') or item.get('news_agency') or '未知来源',
            "author": item.get('data_publisher') or item.get('company_organization') or '未知',
            "time": item.get('source_time', publish_time_str),
            "publishTime": publish_time_str,
            "link": f"/news/{news_id}"
        })
    return formatted_list


# 接下来是那些html文件的渲染，newsdetail主要在后端渲染，其他主要是前端

@app.route('/')
def homepage():
    return render_template('homepage.html')

@app.route('/news/<int:news_id>')
def news_detail(news_id):
    connection = get_db_connection()
    if connection is None:
        return "数据库连接失败", 500

    try:
        with connection.cursor() as cursor:
            #SQL语句，用主键查询各种信息
            sql = """
            SELECT
                nw.id AS news_id,
                tc.title,
                tc.content,
                tc.publish_time,
                i.url AS image_url
            FROM
                news_webpages nw
            JOIN
                text_contents tc ON nw.text_content_id = tc.id
            LEFT JOIN
                images i ON nw.id = i.news_webpage_id
            WHERE
                nw.id = %s
            LIMIT 1;
            """
            cursor.execute(sql, (news_id,))
            article_data = cursor.fetchone()

        if article_data:
            formatted_article = format_news_for_frontend(article_data)[0]
            return render_template('index.html',
                                   title=formatted_article['title'],
                                   publishTime=formatted_article['publishTime'],
                                   image=formatted_article['image'],
                                   content=formatted_article['content'])
        else:
            return "<h1>新闻未找到</h1><p>很抱歉，您请求的新闻不存在。</p><a href='/'>返回首页</a>", 404
    except Exception as e:
        print(f"查询新闻详情失败: {e}")
        return "查询新闻详情失败，请稍后再试。", 500
    finally:
        if connection:
            connection.close()

@app.route('/advanced_search.html')
def advanced_search_page():
    return render_template('advanced_search.html')

@app.route('/delete.html')
def delete_page():
    return render_template('delete.html')

@app.route('/search.html')
def search_page():
    return render_template('search.html')

@app.route('/select.html')
def select_page():
    return render_template('select.html')

@app.route('/menu.html')
def menu_page():
    """渲染登录页面。"""
    return render_template('menu.html')

#接下来是一些API接口
#首页上的每日热点
@app.route('/api/hot_news')
def get_hot_news():
    connection = get_db_connection()
    if connection is None:
        return jsonify({"error": "数据库连接失败"}), 500

    try:
        with connection.cursor() as cursor:
            # 查询最新发布的几条新闻
            sql = """
            SELECT
                nw.id AS news_id,
                tc.title,
                tc.content, -- content will be used for summary
                tc.publish_time,
                i.url AS image_url
            FROM
                news_webpages nw
            JOIN
                text_contents tc ON nw.text_content_id = tc.id
            LEFT JOIN
                images i ON nw.id = i.news_webpage_id
            WHERE
                tc.title != '未找到标题'
            ORDER BY
                tc.publish_time DESC
            LIMIT 5; -- 获取最新的5条新闻
            """
            cursor.execute(sql)
            news_data = cursor.fetchall()

        formatted_news = format_news_for_frontend(news_data)
        return jsonify(formatted_news)
    except Exception as e:
        print(f"获取热点新闻失败: {e}")
        return jsonify({"error": "获取热点新闻失败，请稍后再试。"}), 500
    finally:
        if connection:
            connection.close()

#基础查询功能，
@app.route('/api/query')
def api_query_news():
    keyword = request.args.get('keyword', '').strip()
    if not keyword:
        return jsonify([])

    connection = get_db_connection()
    if connection is None:
        return jsonify({"error": "数据库连接失败"}), 500

    try:
        with connection.cursor() as cursor:
            # 调用 BasicSearch 存储过程
            cursor.callproc('BasicSearch', (keyword,))
            news_data = cursor.fetchall()
            print("从 BasicSearch 获取到的原始数据:", news_data) 

        formatted_news = format_news_for_frontend(news_data)
        return jsonify(formatted_news)
    except Exception as e:
        print(f"调用 BasicSearch 失败: {e}")
        # return jsonify({"error": "查询出错，请稍后再试。"}), 500 
        return jsonify({"error": f"查询出错，请稍后再试: {str(e)}"}), 200
    finally:
        if connection:
            connection.close()

#高级查询功能
@app.route('/api/search', methods=['GET', 'POST'])
def api_search_news():
    connection = get_db_connection()
    if connection is None:
        return jsonify({"error": "数据库连接失败"}), 500

    try:
        with connection.cursor() as cursor:
            if request.method == 'POST': #advanced_search.html
                params = request.get_json()
                keyword = params.get('keyword', '').strip() 
                title_exact = params.get('titleExact', '').strip()
                content_match = params.get('contentMatch', '').strip()
                author_match = params.get('authorMatch', '').strip()
                time_limit_days = int(params.get('timeLimit', 90))
                max_count = int(params.get('maxCount', 100))

                # 高级搜索存储过程的参数：p_某某某
                cursor.callproc('AdvancedSearch', (
                    keyword if keyword else None,
                    title_exact if title_exact else None,
                    content_match if content_match else None,
                    author_match if author_match else None,
                    time_limit_days,
                    max_count
                ))
                news_data = cursor.fetchall()
                
            elif request.method == 'GET': # For delete.html
                keyword = request.args.get('keyword', '').strip()
                if not keyword:
                    return jsonify([])
                
                cursor.callproc('BasicSearch', (keyword,))
                news_data = cursor.fetchall()

        formatted_news = format_news_for_frontend(news_data)
        return jsonify(formatted_news)
    except Exception as e:
        print(f"API搜索失败: {e}")
        # return jsonify({"error": "搜索出错，请稍后再试。"}), 500 
        return jsonify({"error": f"搜索出错，请稍后再试: {str(e)}"}), 200
    finally:
        if connection:
            connection.close()

#使用线程，用户发起要求后，在后台爬虫，用crawler.py
def _run_crawl_and_insert_in_background(query_keyword):
    connection = None # 初始化连接为None
    try:
        print(f"[后台线程] 开始爬取中国新闻网，关键词: {query_keyword}")
        crawled_news_list = crawl_news_from_chinadaily(query_keyword, page_count=3) # 爬取页数，别太多不然慢
        print(f"[后台线程] 爬取完成，获取到 {len(crawled_news_list)} 条新闻。")

        if not crawled_news_list:
            print(f"[后台线程] 未爬取到新闻，关键词: {query_keyword}")
            return

        connection = get_db_connection()
        if connection is None:
            print("[后台线程] 错误: 无法获取数据库连接进行插入操作。")
            return
        #把爬取的信息解析进数据库
        inserted_count = 0
        with connection.cursor() as cursor:
            for news_data in crawled_news_list:
                try:
                    p_keyword = news_data.get('keyword', query_keyword)
                    p_url = news_data.get('link', 'http://example.com/default_link')
                    p_domain = news_data.get('domain', 'default.com')
                    p_company = news_data.get('company', '默认公司')
                    p_contact = news_data.get('contact', 'default@example.com')
                    p_publisher = news_data.get('source', '未知发布者')
                    
                    publish_time_str = news_data.get('time', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                    try:
                        p_publish_time = datetime.datetime.strptime(publish_time_str, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        try:
                            p_publish_time = datetime.datetime.strptime(publish_time_str.split(' ')[0], '%Y-%m-%d')
                        except ValueError:
                            p_publish_time = datetime.datetime.now()

                    p_agency = news_data.get('source', '未知通讯社')
                    p_title = news_data.get('title', '无标题')
                    p_content = news_data.get('content', '无内容')
                    p_visit_count = news_data.get('visit_count', 0)
                    p_image_urls = news_data.get('image', '')
                    p_image_descs = news_data.get('image_desc', '')

                    cursor.callproc('InsertCrawledNews', (
                        p_keyword, p_url, p_domain, p_company, p_contact,
                        p_publisher, p_publish_time, p_agency, p_title, p_content,
                        p_visit_count, p_image_urls, p_image_descs
                    ))
                    inserted_count += 1
                except pymysql.err.IntegrityError as e:
                    if "Duplicate entry" in str(e):
                        print(f"[后台线程] 新闻已存在，跳过插入: {news_data.get('link')}")
                    else:
                        print(f"[后台线程] 批量插入中单条新闻插入失败 (IntegrityError): {e}")
                except Exception as e:
                    print(f"[后台线程] 批量插入中单条新闻插入失败: {news_data.get('title')} - {e}")
        connection.commit()
        print(f"[后台线程] 成功爬取并插入 {inserted_count} 条新闻到数据库。")
    except Exception as e:
        print(f"[后台线程] 数据库操作失败: {e}")
        if connection:
            connection.rollback()
    finally:
        if connection:
            connection.close()

#接下来是API
#进行爬虫的API
@app.route('/api/crawl')
def api_crawl_news():
    query_keyword = request.args.get('keyword', '').strip()
    if not query_keyword:
        return jsonify({"success": False, "error": "请提供爬取关键词"}), 400
    
    thread = threading.Thread(target=_run_crawl_and_insert_in_background, args=(query_keyword,))
    thread.daemon = True 
    thread.start()
    
    return jsonify({"success": True, "message": "爬虫已在后台启动，请稍后刷新页面查看结果。"}), 200

#插入新闻，InsertCrawledNews 存储过程
@app.route('/api/insert', methods=['POST'])
def api_insert_news():
    news_data = request.get_json()
    connection = get_db_connection()
    if connection is None:
        return jsonify({"success": False, "error": "数据库连接失败"}), 500
    
    try:
        with connection.cursor() as cursor:
            p_keyword = news_data.get('keyword', '通用')
            p_url = news_data.get('link', 'http://example.com/default_link')
            p_domain = news_data.get('domain', 'default.com')
            p_company = news_data.get('company', '默认公司')
            p_contact = news_data.get('contact', 'default@example.com')
            p_publisher = news_data.get('source', '未知发布者')
            
            publish_time_str = news_data.get('time', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            try:
                p_publish_time = datetime.datetime.strptime(publish_time_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                p_publish_time = datetime.datetime.now()

            p_agency = news_data.get('source', '未知通讯社')
            p_title = news_data.get('title', '无标题')
            p_content = news_data.get('content', '无内容')
            p_visit_count = news_data.get('visit_count', 0)
            p_image_urls = news_data.get('image', '')
            p_image_descs = news_data.get('image_desc', '')

            cursor.callproc('InsertCrawledNews', (
                p_keyword, p_url, p_domain, p_company, p_contact,
                p_publisher, p_publish_time, p_agency, p_title, p_content,
                p_visit_count, p_image_urls, p_image_descs
            ))
            connection.commit()
            return jsonify({"success": True, "message": "新闻插入成功"})
    except pymysql.err.IntegrityError as e:
        if "Duplicate entry" in str(e) and "for key 'text_contents.title'" in str(e):
             return jsonify({"success": False, "error": "新闻标题已存在，请勿重复插入"}), 409
        elif "Duplicate entry" in str(e) and "for key 'news_webpages.url'" in str(e):
            return jsonify({"success": True, "message": "新闻已存在，跳过插入"})
        else:
             print(f"插入新闻失败 (IntegrityError): {e}")
             connection.rollback()
             return jsonify({"success": False, "error": f"插入失败: {e}"}), 500
    except Exception as e:
        print(f"插入新闻失败: {e}")
        if connection:
            connection.rollback()
        return jsonify({"success": False, "error": f"插入失败，请稍后再试: {e}"}), 500
    finally:
        if connection:
            connection.close()

#一次性插入新闻，循环地InsertCrawledNews
@app.route('/api/insert/bulk', methods=['POST'])
def api_insert_bulk_news():
    news_list = request.get_json()
    inserted_count = 0
    connection = get_db_connection()
    if connection is None:
        return jsonify({"success": False, "error": "数据库连接失败"}), 500

    try:
        with connection.cursor() as cursor:
            for news_data in news_list:
                try:
                    p_keyword = news_data.get('keyword', '通用')
                    p_url = news_data.get('link', 'http://example.com/default_link')
                    p_domain = news_data.get('domain', 'default.com')
                    p_company = news_data.get('company', '默认公司')
                    p_contact = news_data.get('contact', 'default@example.com')
                    p_publisher = news_data.get('source', '未知发布者')
                    
                    publish_time_str = news_data.get('time', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                    try:
                        p_publish_time = datetime.datetime.strptime(publish_time_str, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        try:
                            p_publish_time = datetime.datetime.strptime(publish_time_str.split(' ')[0], '%Y-%m-%d')
                        except ValueError:
                            p_publish_time = datetime.datetime.now()

                    p_agency = news_data.get('source', '未知通讯社')
                    p_title = news_data.get('title', '无标题')
                    p_content = news_data.get('content', '无内容')
                    p_visit_count = news_data.get('visit_count', 0)
                    p_image_urls = news_data.get('image', '')
                    p_image_descs = news_data.get('image_desc', '')

                    cursor.callproc('InsertCrawledNews', (
                        p_keyword, p_url, p_domain, p_company, p_contact,
                        p_publisher, p_publish_time, p_agency, p_title, p_content,
                        p_visit_count, p_image_urls, p_image_descs
                    ))
                    inserted_count += 1
                except pymysql.err.IntegrityError as e:
                    if "Duplicate entry" in str(e):
                        print(f"新闻已存在，跳过插入: {news_data.get('link')}")
                    else:
                        print(f"批量插入中单条新闻插入失败 (IntegrityError): {e}")
                except Exception as e:
                    print(f"批量插入中单条新闻插入失败: {news_data.get('title')} - {e}")
        connection.commit()
        return jsonify({"success": True, "message": f"成功插入 {inserted_count} 条新闻"})
    except Exception as e:
        print(f"批量插入新闻失败: {e}")
        if connection:
            connection.rollback()
        return jsonify({"success": False, "error": f"批量插入失败，请稍后再试: {e}"}), 500
    finally:
        if connection:
            connection.close()

#删除新闻
@app.route('/api/delete', methods=['POST'])
def api_delete_news():
    news_data = request.get_json()
    news_id_to_delete = news_data.get('id')
    if not news_id_to_delete:
        return jsonify({"success": False, "error": "未提供新闻ID"}), 400

    connection = get_db_connection()
    if connection is None:
        return jsonify({"success": False, "error": "数据库连接失败"}), 500

    try:
        with connection.cursor() as cursor:
            cursor.callproc('DeleteNewsPage', (news_id_to_delete,))
            connection.commit()
            return jsonify({"success": True, "message": "新闻删除成功"})
    except Exception as e:
        print(f"删除新闻失败: {e}")
        if connection:
            connection.rollback()
        return jsonify({"success": False, "error": f"删除失败，请稍后再试: {e}"}), 500
    finally:
        if connection:
            connection.close()

#一次性删除，循环DeleteNewsPage
@app.route('/api/delete/bulk', methods=['POST'])
def api_delete_bulk_news():
    news_list_to_delete = request.get_json()
    deleted_count = 0
    connection = get_db_connection()
    if connection is None:
        return jsonify({"success": False, "error": "数据库连接失败"}), 500

    try:
        with connection.cursor() as cursor:
            for news_data in news_list_to_delete:
                news_id = news_data.get('id')
                if news_id:
                    try:
                        cursor.callproc('DeleteNewsPage', (news_id,))
                        deleted_count += 1
                    except Exception as e:
                        print(f"批量删除中单条新闻删除失败 (ID: {news_id}): {e}")
                        #与别的事务不同，跳过而不是回滚
            connection.commit()
        return jsonify({"success": True, "message": f"成功删除 {deleted_count} 条新闻"})
    except Exception as e:
        print(f"批量删除新闻失败: {e}")
        if connection:
            connection.rollback() #这里才会回滚
        return jsonify({"success": False, "error": f"批量删除失败，请稍后再试: {e}"}), 500
    finally:
        if connection:
            connection.close()



#定时爬取功能，丰富数据库
from apscheduler.schedulers.background import BackgroundScheduler
import random

def scheduled_crawl_news():

  keywords = ["国际","时评","外交"]
  keyword = random.choice(keywords)
  print(f"[定时任务] {datetime.datetime.now()}: 开始爬取，关键词: {keyword}")
  _run_crawl_and_insert_in_background(keyword)

scheduler = BackgroundScheduler()

if __name__ == '__main__':
 scheduler.add_job(scheduled_crawl_news, 'interval', hours=24, id='crawl_news_job')
 scheduler.start()

 try:
  app.run(debug=True, port=5000, host='0.0.0.0')
 except (KeyboardInterrupt, SystemExit):
  scheduler.shutdown()


if __name__ == '__main__':
    app.run(debug=True, port=5000, host = '0.0.0.0')

