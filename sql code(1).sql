-- 新闻爬虫数据库

-- 创建数据库
CREATE DATABASE IF NOT EXISTS news_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE news_db;

-- 1. 新闻网站表
CREATE TABLE IF NOT EXISTS news_websites (
    id INT AUTO_INCREMENT PRIMARY KEY,
    domain VARCHAR(255) NOT NULL COMMENT '网站域名',
    company_organization VARCHAR(255) COMMENT '所属公司或组织',
    contact_info TEXT COMMENT '联系信息'
);

-- 2. 数据源信息表
CREATE TABLE IF NOT EXISTS data_sources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    data_publisher VARCHAR(255) COMMENT '数据发布者',
    publish_time DATETIME COMMENT '发布时间',
    original_data_link TEXT COMMENT '原数据链接'
);

-- 3. 关键字段表
CREATE TABLE IF NOT EXISTS keyword_fields (
    id INT AUTO_INCREMENT PRIMARY KEY,
    keyword VARCHAR(255) UNIQUE NOT NULL COMMENT '关键字'
);

-- 4. 文本内容表
CREATE TABLE IF NOT EXISTS text_contents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    news_agency VARCHAR(255) COMMENT '通讯社',
    publish_time DATETIME COMMENT '发布时间',
    title VARCHAR(255) NOT NULL COMMENT '新闻标题',
    content TEXT COMMENT '新闻正文'
);

-- 5. 新闻网页表
CREATE TABLE IF NOT EXISTS news_webpages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    url TEXT NOT NULL COMMENT '网页URL',
    crawl_time DATETIME COMMENT '抓取时间',
    visit_count INT DEFAULT 0 COMMENT '访问量',
    news_website_id INT COMMENT '所属网站ID',
    data_source_id INT COMMENT '数据源ID',
    text_content_id INT UNIQUE COMMENT '关联文本内容ID',
    FOREIGN KEY (news_website_id) REFERENCES news_websites(id),
    FOREIGN KEY (data_source_id) REFERENCES data_sources(id),
    FOREIGN KEY (text_content_id) REFERENCES text_contents(id)
);

-- 6. 图片表
CREATE TABLE IF NOT EXISTS images (
    id INT AUTO_INCREMENT PRIMARY KEY,
    url TEXT NOT NULL COMMENT '图片URL',
    description TEXT COMMENT '图片描述',
    news_webpage_id INT COMMENT '关联的新闻网页ID',
    FOREIGN KEY (news_webpage_id) REFERENCES news_webpages(id)
);

-- 7. 多对多关系表：新闻网页-关键字
CREATE TABLE IF NOT EXISTS news_webpage_keywords (
    news_webpage_id INT,
    keyword_field_id INT,
    PRIMARY KEY (news_webpage_id, keyword_field_id),
    FOREIGN KEY (news_webpage_id) REFERENCES news_webpages(id),
    FOREIGN KEY (keyword_field_id) REFERENCES keyword_fields(id)
);

-- 添加常用索引
CREATE INDEX idx_publish_time ON text_contents(publish_time);
CREATE INDEX idx_keyword ON keyword_fields(keyword);


-- 插入新闻
DELIMITER $$

DROP PROCEDURE IF EXISTS InsertCrawledNews$$

CREATE PROCEDURE InsertCrawledNews(
    IN p_keyword VARCHAR(255),           -- 关键字
    IN p_url TEXT,                       -- 网页URL
    IN p_domain VARCHAR(255),            -- 网站域名
    IN p_company VARCHAR(255),           -- 网站公司
    IN p_contact TEXT,                   -- 网站联系方式
    IN p_publisher VARCHAR(255),         -- 数据发布者
    IN p_publish_time DATETIME,          -- 发布时间
    IN p_agency VARCHAR(255),            -- 通讯社
    IN p_title VARCHAR(255),             -- 新闻标题
    IN p_content TEXT,                   -- 新闻正文
    IN p_visit_count INT,                -- 访问量
    IN p_image_urls TEXT,                -- 图片URLs
    IN p_image_descs TEXT                -- 图片描述
)
BEGIN
    DECLARE v_webpage_id INT;
    DECLARE v_website_id INT;
    DECLARE v_source_id INT;
    DECLARE v_content_id INT;
    DECLARE v_keyword_id INT;
    DECLARE v_image_count INT;
    DECLARE v_i INT DEFAULT 1;
    DECLARE v_image_url TEXT;
    DECLARE v_image_desc TEXT;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;
    
    START TRANSACTION;
    
    SELECT id INTO v_webpage_id FROM news_webpages WHERE url = p_url LIMIT 1;
    
    IF v_webpage_id IS NULL THEN
        -- 插入新网站
        INSERT INTO news_websites (domain, company_organization, contact_info)
        VALUES (p_domain, p_company, p_contact)
        ON DUPLICATE KEY UPDATE id = id;
        SET v_website_id = LAST_INSERT_ID();
        
        -- 插入数据源
        INSERT INTO data_sources (data_publisher, publish_time, original_data_link)
        VALUES (p_publisher, p_publish_time, p_url);
        SET v_source_id = LAST_INSERT_ID();
        
        -- 插入文本内容
        INSERT INTO text_contents (news_agency, publish_time, title, content)
        VALUES (p_agency, p_publish_time, p_title, p_content);
        SET v_content_id = LAST_INSERT_ID();
        
        -- 插入新闻网页
        INSERT INTO news_webpages (url, crawl_time, visit_count, news_website_id, data_source_id, text_content_id)
        VALUES (p_url, NOW(), p_visit_count, v_website_id, v_source_id, v_content_id);
        SET v_webpage_id = LAST_INSERT_ID();
        
        -- 插入图片
        IF p_image_urls IS NOT NULL AND LENGTH(p_image_urls) > 0 THEN
            -- 计算图片数量
            SET v_image_count = (LENGTH(p_image_urls) - LENGTH(REPLACE(p_image_urls, ',', ''))) + 1;
            
            -- 循环插入每张图片
            WHILE v_i <= v_image_count DO
                -- 提取单个图片URL和描述
                SET v_image_url = SUBSTRING_INDEX(SUBSTRING_INDEX(p_image_urls, ',', v_i), ',', -1);
                SET v_image_desc = SUBSTRING_INDEX(SUBSTRING_INDEX(p_image_descs, ',', v_i), ',', -1);
                
                INSERT INTO images (url, description, news_webpage_id)
                VALUES (v_image_url, v_image_desc, v_webpage_id);
                
                SET v_i = v_i + 1;
            END WHILE;
        END IF;
    END IF;
    
    -- 获取或插入关键字
    SELECT id INTO v_keyword_id FROM keyword_fields WHERE keyword = p_keyword LIMIT 1;
    IF v_keyword_id IS NULL THEN
        INSERT INTO keyword_fields (keyword) VALUES (p_keyword);
        SET v_keyword_id = LAST_INSERT_ID();
    END IF;
    
    -- 关联关键字和新闻网页
    IF v_webpage_id IS NOT NULL AND v_keyword_id IS NOT NULL THEN
        INSERT INTO news_webpage_keywords (news_webpage_id, keyword_field_id)
        VALUES (v_webpage_id, v_keyword_id)
        ON DUPLICATE KEY UPDATE news_webpage_id = news_webpage_id;
    END IF;
    
    COMMIT;
END$$

DELIMITER ;


-- 删除新闻
DELIMITER $$

DROP PROCEDURE IF EXISTS DeleteNewsPage$$

CREATE PROCEDURE DeleteNewsPage(IN p_webpage_id INT)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;
    
    START TRANSACTION;
    
    -- 删除图片
    DELETE i 
    FROM images i
    WHERE i.news_webpage_id = p_webpage_id;
    
    -- 删除关联关系
    DELETE nwk 
    FROM news_webpage_keywords nwk
    WHERE nwk.news_webpage_id = p_webpage_id;
    
    -- 删除新闻网页
    DELETE nw 
    FROM news_webpages nw
    WHERE nw.id = p_webpage_id;
    
    -- 删除孤立的内容、数据源和网站
    DELETE tc 
    FROM text_contents tc
    LEFT JOIN news_webpages nw ON tc.id = nw.text_content_id
    WHERE nw.id IS NULL;
    
    DELETE ds 
    FROM data_sources ds
    LEFT JOIN news_webpages nw ON ds.id = nw.data_source_id
    WHERE nw.id IS NULL;
    
    DELETE ns 
    FROM news_websites ns
    LEFT JOIN news_webpages nw ON ns.id = nw.news_website_id
    WHERE nw.id IS NULL;
    
    -- 删除孤立关键字
    WITH orphan_keywords AS (
        SELECT kf.id 
        FROM keyword_fields kf
        LEFT JOIN news_webpage_keywords nwk ON kf.id = nwk.keyword_field_id
        WHERE nwk.keyword_field_id IS NULL
    )
    DELETE kf 
    FROM keyword_fields kf
    WHERE kf.id IN (SELECT id FROM orphan_keywords);
    
    COMMIT;
END$$

DELIMITER ;




-- 基础搜索
DELIMITER $$

DROP PROCEDURE IF EXISTS BasicSearch$$

CREATE PROCEDURE BasicSearch(IN p_text VARCHAR(255))
BEGIN
    SELECT
        nw.id AS news_id,
        nw.url AS webpage_url,
        nw.visit_count,
        nw.crawl_time,
        ns.domain AS website_domain,
        ns.company_organization,
        ds.data_publisher,
        ds.publish_time AS source_time,
        tc.news_agency,
        tc.title,
        tc.content,
        i.url AS image_url,
        i.description AS image_desc
    FROM
        news_webpages nw
        JOIN news_websites ns ON nw.news_website_id = ns.id
        JOIN data_sources ds ON nw.data_source_id = ds.id
        JOIN text_contents tc ON nw.text_content_id = tc.id
        JOIN news_webpage_keywords nwk ON nw.id = nwk.news_webpage_id
        JOIN keyword_fields kf ON nwk.keyword_field_id = kf.id
        LEFT JOIN images i ON nw.id = i.news_webpage_id
    WHERE
        kf.keyword = p_text
        OR ns.company_organization LIKE CONCAT('%', p_text, '%')
        OR tc.news_agency LIKE CONCAT('%', p_text, '%')
        OR tc.title LIKE CONCAT('%', p_text, '%')
        OR tc.content LIKE CONCAT('%', p_text, '%')
    ORDER BY
        tc.publish_time DESC;
END$$

DELIMITER ;


-- 高级搜索
DELIMITER $$

DROP PROCEDURE IF EXISTS AdvancedSearch$$

CREATE PROCEDURE AdvancedSearch(
    IN p_keyword VARCHAR(255),
    IN p_title VARCHAR(255),
    IN p_content TEXT,
    IN p_agency VARCHAR(255),
    IN p_days INT,
    IN p_limit INT
)
BEGIN
    SELECT
        nw.id AS news_id,
        nw.url AS webpage_url,
        nw.visit_count,
        nw.crawl_time,
        ns.domain AS website_domain,
        ns.company_organization,
        ds.data_publisher,
        ds.publish_time AS source_time,
        tc.news_agency,
        tc.title,
        tc.content,
        i.url AS image_url,
        i.description AS image_desc
    FROM
        news_webpages nw
        JOIN news_websites ns ON nw.news_website_id = ns.id
        JOIN data_sources ds ON nw.data_source_id = ds.id
        JOIN text_contents tc ON nw.text_content_id = tc.id
        JOIN news_webpage_keywords nwk ON nw.id = nwk.news_webpage_id
        JOIN keyword_fields kf ON nwk.keyword_field_id = kf.id
        LEFT JOIN images i ON nw.id = i.news_webpage_id
    WHERE
        (p_keyword IS NULL OR kf.keyword = p_keyword)
        AND (p_title IS NULL OR tc.title LIKE CONCAT('%', p_title, '%'))
        AND (p_content IS NULL OR tc.content LIKE CONCAT('%', p_content, '%'))
        AND (p_agency IS NULL OR tc.news_agency LIKE CONCAT('%', p_agency, '%'))
        AND tc.publish_time >= NOW() - INTERVAL p_days DAY
    ORDER BY
        tc.publish_time DESC
    LIMIT p_limit;
END$$

DELIMITER ;


-- 基础搜索视图
DROP VIEW IF EXISTS BasicSearchView;

CREATE VIEW BasicSearchView AS
SELECT 
    nw.url AS webpage_url,          
    nw.visit_count,                 
    nw.crawl_time,                  
    ns.domain AS website_domain,    
    ns.company_organization,        
    ds.data_publisher,              
    ds.publish_time AS source_time, 
    tc.news_agency,                 
    tc.title,                       
    tc.content,                     
    i.url AS image_url,             
    i.description AS image_desc     
FROM 
    news_webpages nw
    JOIN news_websites ns ON nw.news_website_id = ns.id
    JOIN data_sources ds ON nw.data_source_id = ds.id
    JOIN text_contents tc ON nw.text_content_id = tc.id
    JOIN news_webpage_keywords nwk ON nw.id = nwk.news_webpage_id
    JOIN keyword_fields kf ON nwk.keyword_field_id = kf.id
    LEFT JOIN images i ON nw.id = i.news_webpage_id
ORDER BY 
    tc.publish_time DESC;


-- 高级搜索视图
DROP VIEW IF EXISTS AdvancedSearchView;

CREATE VIEW AdvancedSearchView AS
SELECT 
    nw.url AS webpage_url,          
    nw.visit_count,                 
    nw.crawl_time,                  
    ns.domain AS website_domain,    
    ns.company_organization,        
    ds.data_publisher,              
    ds.publish_time AS source_time, 
    tc.news_agency,                 
    tc.title,                       
    tc.content,                     
    i.url AS image_url,             
    i.description AS image_desc     
FROM 
    news_webpages nw
    JOIN news_websites ns ON nw.news_website_id = ns.id
    JOIN data_sources ds ON nw.data_source_id = ds.id
    JOIN text_contents tc ON nw.text_content_id = tc.id
    JOIN news_webpage_keywords nwk ON nw.id = nwk.news_webpage_id
    JOIN keyword_fields kf ON nwk.keyword_field_id = kf.id
    LEFT JOIN images i ON nw.id = i.news_webpage_id
ORDER BY 
    tc.publish_time DESC;
