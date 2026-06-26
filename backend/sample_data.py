from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Shanghai")


def google_news_url(query: str) -> str:
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"


def sample_articles() -> list[dict]:
    yesterday = datetime.now(TZ) - timedelta(days=1)
    base = yesterday.replace(hour=20, minute=30, second=0, microsecond=0)
    return [
        {
            "title": "茶饮品牌「爷爷不泡茶」海外首店落地新加坡，首日排队超过300米",
            "url": "https://www.example.com/sample/grandpa-tea-singapore",
            "source_name": "样例信源",
            "source_type": "公开资讯平台",
            "published_at": base.isoformat(),
            "excerpt": "品牌在海外首店正式落地新加坡核心商圈，社交平台出现大量打卡与排队内容。",
            "content": "爷爷不泡茶海外首店落地新加坡，首日排队超过300米。门店位于核心商圈，产品以东方茶饮和地域文化表达为主，社交平台出现大量打卡内容。品牌近年在国内多城加速开店，具备持续拓店和年轻客群吸引力。",
        },
        {
            "title": "甜品品牌「Sachertorte」完成千万欧元A轮融资，计划进入亚洲购物中心",
            "url": "https://www.example.com/sample/sachertorte-funding",
            "source_name": "样例信源",
            "source_type": "国际媒体",
            "published_at": (base - timedelta(hours=1)).isoformat(),
            "excerpt": "欧洲新兴甜品品牌完成新一轮融资，将重点拓展亚洲和中东市场。",
            "content": "Sachertorte完成千万欧元A轮融资，投资方看好其精品甜品和门店模型。品牌计划未来两年在亚洲开设50家门店，重点进入购物中心和高势能商圈。",
        },
        {
            "title": "零食品牌「零食很忙」全国门店突破4000家，进入东南亚市场",
            "url": "https://www.example.com/sample/snack-expansion",
            "source_name": "样例信源",
            "source_type": "行业媒体",
            "published_at": (base - timedelta(hours=2)).isoformat(),
            "excerpt": "全国门店数量继续提升，同时宣布首批海外市场计划。",
            "content": "零食很忙全国门店突破4000家，同时宣布进入东南亚市场。品牌强调供应链优势和高性价比模型，未来将重点寻找社区商业和购物中心轻量化门店位置。",
        },
        {
            "title": "潮玩品牌「TOYCITY」联名LABUBU系列盲盒引发多平台抢购",
            "url": "https://www.example.com/sample/toycity-labubu",
            "source_name": "样例信源",
            "source_type": "社媒公开页",
            "published_at": (base - timedelta(hours=3)).isoformat(),
            "excerpt": "联名款发售后出现抢购和二级市场溢价，线下快闪排队明显。",
            "content": "TOYCITY与LABUBU推出联名盲盒后，多平台出现抢购，部分款式二级市场溢价达到3-5倍。品牌计划在核心城市继续做线下快闪和集合店合作。",
        },
        {
            "title": "健康轻食品牌「KeepFit Kitchen」完成近亿元B轮融资，将加码线下门店",
            "url": "https://www.example.com/sample/keepfit-funding",
            "source_name": "样例信源",
            "source_type": "融资动态",
            "published_at": (base - timedelta(hours=4)).isoformat(),
            "excerpt": "健康餐饮品牌获得资金支持，计划在一线和新一线城市拓展门店。",
            "content": "KeepFit Kitchen完成近亿元人民币B轮融资，将用于产品研发、供应链升级和线下门店扩张。品牌主打低卡轻食和运动人群餐饮场景，适合办公商业和生活方式型购物中心。",
        },
        {
            "title": "咖啡烘焙品牌「野人先生」完成新一轮融资，加速供应链建设",
            "url": "https://www.example.com/sample/wildman-coffee",
            "source_name": "样例信源",
            "source_type": "公开资讯平台",
            "published_at": (base - timedelta(hours=5)).isoformat(),
            "excerpt": "咖啡烘焙品牌扩展门店后厨和供应链体系，关注社区店与商场店。",
            "content": "野人先生完成新一轮融资，将用于烘焙工厂和门店后厨建设。品牌以精品咖啡和现烤烘焙结合为特色，近期在多个城市开出购物中心门店。",
        },
        {
            "title": "香氛集合品牌「ScentLab」首店开业三日销售破百万，年轻客群占比超70%",
            "url": "https://www.example.com/sample/scentlab-opening",
            "source_name": "样例信源",
            "source_type": "品牌官网",
            "published_at": (base - timedelta(hours=6)).isoformat(),
            "excerpt": "新锐香氛集合品牌首店表现亮眼，正在寻找全国高质量购物中心点位。",
            "content": "ScentLab首店开业三日销售突破百万，年轻客群占比超过70%。品牌主打原创香氛、香水实验室和体验式零售，计划在全国核心购物中心拓展旗舰店和快闪店。",
        },
        {
            "title": "国内新锐烘焙品牌「酥山」武汉首店开业，开业周末连续售罄",
            "url": "https://www.example.com/sample/sushan-wuhan-first-store",
            "source_name": "样例信源",
            "source_type": "互联网搜索",
            "published_at": (base - timedelta(hours=7)).isoformat(),
            "excerpt": "本土新锐烘焙品牌首进武汉，门店主打国潮点心和现烤体验，社媒打卡热度升温。",
            "content": "国内新锐烘焙品牌酥山武汉首店开业，开业周末多款产品连续售罄。品牌主打国潮点心、现烤体验和年轻化包装，此前已在杭州、成都开出小体量门店，正在寻找核心购物中心和街区商业点位。",
        },
    ]


DEFAULT_SOURCES = [
    {
        "name": "36氪新消费",
        "source_type": "公开资讯平台",
        "url": "https://36kr.com/",
        "adapter": "html",
        "enabled": 1,
        "notes": "优先级A；高质量公开媒体。用于发现融资、消费品牌和新商业模式资讯；需过滤泛科技和成熟公司常规动态。",
    },
    {
        "name": "赢商网",
        "source_type": "商业地产媒体",
        "url": "https://www.winshang.com/",
        "adapter": "html",
        "enabled": 1,
        "notes": "优先级S；高质量首店/商业地产源。用于发现首店、新开业、购物中心品牌入驻和招商动态。",
    },
    {
        "name": "Foodaily",
        "source_type": "食品饮料媒体",
        "url": "https://www.foodaily.com/",
        "adapter": "html",
        "enabled": 1,
        "notes": "优先级A；高质量食品饮料媒体。用于发现食品饮料新品、爆品、新锐品牌和品类趋势。",
    },
    {
        "name": "品牌星球",
        "source_type": "品牌媒体",
        "url": "https://www.brandstar.com.cn/",
        "adapter": "html",
        "enabled": 1,
        "notes": "优先级A；高质量品牌媒体。用于发现新品牌、DTC、品牌升级、内容种草和消费趋势。",
    },
    {
        "name": "Google News 新消费品牌搜索",
        "source_type": "公开资讯平台",
        "url": "https://news.google.com/rss/search?q=%E6%96%B0%E6%B6%88%E8%B4%B9%20%E7%88%86%E6%AC%BE%20%E5%93%81%E7%89%8C%20OR%20%E9%A6%96%E5%BA%97%20OR%20%E8%9E%8D%E8%B5%84%20OR%20%E5%BC%80%E5%BA%97&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "adapter": "rss",
        "enabled": 1,
        "notes": "优先级A；精准新闻聚合。用于发现全国/国际新消费、首店、融资、开店和爆款品牌资讯。",
    },
    {
        "name": "红餐网",
        "source_type": "餐饮行业媒体",
        "url": "https://www.canyin88.com/",
        "adapter": "html",
        "enabled": 1,
        "notes": "优先级S；高质量餐饮行业源。关注餐饮新品牌、品类变化、连锁扩张、开业、加盟、茶饮、咖啡、烘焙、小吃。",
    },
    {
        "name": "FoodTalks 全球食品资讯",
        "source_type": "食品饮料媒体",
        "url": "https://www.foodtalks.cn/news",
        "adapter": "html",
        "enabled": 1,
        "notes": "优先级A；高质量食品饮料创新源。关注新品、爆品、创新、饮料、零食、茶饮、咖啡、包装和供应链。",
    },
    {
        "name": "FBIF 食品饮料创新",
        "source_type": "食品饮料媒体",
        "url": "https://www.foodtalks.cn/fbif",
        "adapter": "html",
        "enabled": 1,
        "notes": "优先级A；高质量食品饮料创新与品牌案例源。关注食饮创新、年度榜单、展会、品牌案例和新品类。",
    },
    {
        "name": "饮品报",
        "source_type": "饮品行业媒体",
        "url": "https://www.drinknewspaper.com/",
        "adapter": "html",
        "enabled": 1,
        "notes": "优先级A；高质量饮品垂直源。关注奶茶、咖啡、茶饮、甜品、饮品创业、门店创新和新品牌。",
    },
    {
        "name": "联商网",
        "source_type": "零售/商业地产媒体",
        "url": "https://www.linkshop.com/",
        "adapter": "html",
        "enabled": 1,
        "notes": "优先级A；高质量零售商业源。关注零售、商超、购物中心、首店、开业和品牌入驻。",
    },
    {
        "name": "中购联",
        "source_type": "商业地产媒体",
        "url": "https://www.irgroad.com/",
        "adapter": "html",
        "enabled": 1,
        "notes": "优先级B；商业地产/购物中心行业源。关注购物中心、商业项目、业态创新、行业会议和报告。",
    },
    {
        "name": "RET 睿意德",
        "source_type": "商业地产服务机构",
        "url": "https://www.ret.cn/",
        "adapter": "html",
        "enabled": 1,
        "notes": "优先级B；高质量商业地产研究源。关注城市商业、购物中心、项目调改、业态组合和资产运营趋势。",
    },
    {
        "name": "亿邦动力",
        "source_type": "电商/零售媒体",
        "url": "https://www.ebrun.com/",
        "adapter": "html",
        "enabled": 1,
        "notes": "优先级A；高质量零售与电商媒体。关注零售、电商、新消费、产业互联网、品牌增长和渠道变化。",
    },
    {
        "name": "壹览商业",
        "source_type": "大消费媒体",
        "url": "https://www.yilantop.com/",
        "adapter": "html",
        "enabled": 1,
        "notes": "优先级A；大消费行业源。关注新消费、连锁咖啡、茶饮、融资、零售和品牌扩张。",
    },
    {
        "name": "消费界",
        "source_type": "新消费媒体",
        "url": "https://www.eeeck.com/news/",
        "adapter": "html",
        "enabled": 1,
        "notes": "优先级A；新消费垂直源。关注新兴消费、新品牌、消费趋势和品牌动态。",
    },
    {
        "name": "Google News 餐饮新品牌",
        "source_type": "公开资讯平台",
        "url": google_news_url("餐饮 新品牌 OR 餐饮 爆火"),
        "adapter": "rss",
        "enabled": 1,
        "notes": "优先级A；精准新闻聚合。聚合餐饮新品牌、爆火、开业和连锁扩张报道。",
    },
    {
        "name": "Google News 武汉首店新店",
        "source_type": "公开资讯平台",
        "url": google_news_url("武汉 首店 OR 武汉 新店 OR 光谷 新店"),
        "adapter": "rss",
        "enabled": 1,
        "notes": "优先级S；本地高相关新闻聚合。捕捉武汉/光谷首店、新店、开业和购物中心入驻报道。",
    },
    {
        "name": "Google News 茶饮咖啡",
        "source_type": "公开资讯平台",
        "url": google_news_url("茶饮 咖啡 新品牌 开店"),
        "adapter": "rss",
        "enabled": 1,
        "notes": "优先级A；精准新闻聚合。捕捉茶饮、咖啡、新品牌、新开店和排队爆火报道。",
    },
    {
        "name": "Google News 购物中心品牌入驻",
        "source_type": "公开资讯平台",
        "url": google_news_url("购物中心 品牌入驻 首店 开业"),
        "adapter": "rss",
        "enabled": 1,
        "notes": "优先级A；精准新闻聚合。捕捉购物中心品牌入驻、首店、开业和招商动态。",
    },
    {
        "name": "Google News 消费品牌融资",
        "source_type": "公开资讯平台",
        "url": google_news_url("消费品牌 融资 OR 新消费 融资"),
        "adapter": "rss",
        "enabled": 1,
        "notes": "优先级A；精准新闻聚合。捕捉消费品牌融资、新消费融资和后续线下扩张机会。",
    },
    {
        "name": "互联网搜索：国内新兴品牌",
        "source_type": "互联网搜索",
        "url": "search://domestic-emerging-brands",
        "adapter": "web_search",
        "enabled": 1,
        "notes": (
            "通过 SEARCH_PROVIDER 对应的搜索 API Key 搜索新店、新品牌、首店、国货和新锐消费品牌。"
            "queries:\n"
            "国内 新兴品牌 新店 开业\n"
            "中国 新品牌 首店 购物中心\n"
            "新锐消费品牌 融资 开店\n"
            "国货品牌 首店 新店\n"
            "本土品牌 小红书 爆火 门店\n"
            "餐饮 新品牌 新店 开业\n"
            "美妆 香氛 新锐品牌 首店\n"
            "潮玩 文创 新品牌 快闪"
        ),
    },
    {
        "name": "互联网搜索：武汉光谷新店",
        "source_type": "互联网搜索",
        "url": "search://wuhan-guanggu-new-stores",
        "adapter": "web_search",
        "enabled": 1,
        "notes": (
            "优先级S；本地高相关搜索源，只保留武汉/光谷新店、首店、开业、排队和品牌入驻线索。"
            "queries:\n"
            "武汉 新店 开业 首店 排队\n"
            "光谷 新店 开业 首店 排队\n"
            "世界城 光谷步行街 新店 开业\n"
            "武汉 首店 品牌 入驻 购物中心"
        ),
    },
    {
        "name": "互联网搜索：茶饮咖啡烘焙新品牌",
        "source_type": "互联网搜索",
        "url": "search://beverage-coffee-bakery-emerging",
        "adapter": "web_search",
        "enabled": 1,
        "notes": (
            "优先级A；高质量垂直搜索源，聚焦茶饮、咖啡、烘焙新品牌和开店爆火信号。"
            "queries:\n"
            "茶饮 新品牌 爆火 开店 排队\n"
            "咖啡 新品牌 连锁 开店 爆火\n"
            "烘焙 新品牌 面包店 爆火 排队\n"
            "新中式 烘焙 首店 新店"
        ),
    },
    {
        "name": "互联网搜索：零售生活方式新品牌",
        "source_type": "互联网搜索",
        "url": "search://retail-lifestyle-emerging",
        "adapter": "web_search",
        "enabled": 1,
        "notes": (
            "优先级A；垂直搜索源，聚焦零食集合店、潮玩、宠物友好和运动户外等线下消费机会。"
            "queries:\n"
            "零食集合店 新品牌 折扣零食 开店\n"
            "潮玩 IP 新品牌 快闪 联名\n"
            "宠物消费 新品牌 宠物友好 商场\n"
            "户外 运动 新消费 品牌 门店"
        ),
    },
    {
        "name": "社媒公开页",
        "source_type": "社媒公开页",
        "url": "https://www.xiaohongshu.com/explore",
        "adapter": "html",
        "enabled": 0,
        "notes": "默认关闭。当前阶段不启用低信噪比泛社媒公开页；后续通过千瓜/新榜/蝉妈妈/飞瓜等高质量导入或API接入。",
    },
]
