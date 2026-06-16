#!/usr/bin/env python3
"""بوت الجيميلات v3.0 - النسخة الكاملة"""

import logging, json, re, os, random, string, httpx
from datetime import datetime
from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler,
)

# ══════════════════════════════════════════════════════
# الإعدادات
# ══════════════════════════════════════════════════════
BOT_TOKEN        = "7772742859:AAGWIVRg6D6OP4Zgsr2C2MddAEGkXk_8Kdw"
ADMIN_ID         = 8217513989
CHANNEL_USERNAME = "@TESLA_TEAMI"
PROOFS_CHANNEL   = "@TESLA_PRO1"
GROQ_API_KEY     = "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"
DATA_FILE        = "bot_data.json"
MIN_WITHDRAW     = 5

# ══════════════════════════════════════════════════════
# الحالات
# ══════════════════════════════════════════════════════
(MAIN_MENU, DELIVER_GMAIL, CONFIRM_GMAIL, WITHDRAW_NUMBER,
 WITHDRAW_CONFIRM_NUM, WITHDRAW_NAME, ADD_CHANNEL) = range(7)

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

groq_client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL  = "llama-3.3-70b-versatile"

# ══════════════════════════════════════════════════════
# البيانات الدائمة (ملف JSON)
# ══════════════════════════════════════════════════════
def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE,"r",encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {"users":{},"banned_users":[],"blocked_bot":[],"delivered_gmails":[]}

def save_db():
    try:
        with open(DATA_FILE,"w",encoding="utf-8") as f:
            json.dump(db,f,ensure_ascii=False,indent=2)
    except Exception as e:
        logger.error(f"save_db: {e}")

db = load_db()

def get_user(uid):
    k = str(uid)
    if k not in db["users"]:
        db["users"][k] = {"balance":0.0,"wallets":[],"first_name":"","username":"","joined":datetime.now().isoformat(),"gmails":0}
    return db["users"][k]

def add_balance(uid, amount):
    u = get_user(uid); u["balance"] = round(u["balance"]+amount,2); save_db()

def get_balance(uid):
    return get_user(uid).get("balance",0)

def is_banned(uid):
    return uid in db.get("banned_users",[])

def gen_id():
    return ''.join(random.choices(string.ascii_lowercase+string.digits,k=8))

# ══════════════════════════════════════════════════════
# إعدادات البوت (في الذاكرة)
# ══════════════════════════════════════════════════════
bot_config = {
    "names":[],"password":"","format_template":"","prices":"",
    "price_per_gmail":0,"channel":CHANNEL_USERNAME,"extra_channels":[],
    "bot_name":"بوت الجيميلات","welcome_msg":"👋 مرحباً {name}!\nاختر ما تريد:","developer":"@T_TSLA",
}

all_users        = set()
ai_convs         = {}
pending_gmail    = {}   # uid → email
pending_reviews  = {}   # rid → {uid,gmail,username,first_name}
pending_wdraw    = {}   # rid → {uid,amount,wallet}

# ══════════════════════════════════════════════════════
# AI
# ══════════════════════════════════════════════════════
ADMIN_SYS = (
    "أنت مساعد ذكاء اصطناعي (sub-admin) لبوت تلجرام للجيميلات.\n"
    "لديك صلاحية كاملة لتنفيذ أوامر على البوت. الأدمن الأكبر منك هو مالك البوت.\n"
    "عندما يطلب الأدمن تنفيذ عملية، ضع الأمر بالصيغة:\n"
    "[[CMD:{\"action\":\"اسم\", ...}]]\n\n"
    "الأوامر:\n"
    "broadcast: {\"action\":\"broadcast\",\"message\":\"نص\"}\n"
    "add_channel: {\"action\":\"add_channel\",\"channel\":\"@ch\"}\n"
    "remove_channel: {\"action\":\"remove_channel\",\"channel\":\"@ch\"}\n"
    "set_names: {\"action\":\"set_names\",\"names\":[\"name1\",\"name2\"]}\n"
    "set_password: {\"action\":\"set_password\",\"password\":\"pass\"}\n"
    "set_format: {\"action\":\"set_format\",\"format\":\"fmt\"}\n"
    "set_prices: {\"action\":\"set_prices\",\"prices\":\"text\"}\n"
    "set_price_per_gmail: {\"action\":\"set_price_per_gmail\",\"price\":8}\n"
    "clear_names: {\"action\":\"clear_names\"}\n"
    "ban_user: {\"action\":\"ban_user\",\"user_id\":123}\n"
    "unban_user: {\"action\":\"unban_user\",\"user_id\":123}\n"
    "set_welcome: {\"action\":\"set_welcome\",\"message\":\"نص\"}\n"
    "set_bot_name: {\"action\":\"set_bot_name\",\"name\":\"اسم\"}\n\n"
    "قواعد: نفذ الطلب فوراً بالأمر المناسب. تكلم بالعربي.\n"
    "البيانات الحالية:\n{config}"
)
USER_SYS = "أنت مساعد بوت الجيميلات. ساعد في الجيميلات والأسعار فقط.\nالبيانات:\n{config}"

def get_ai_resp(uid, msg, is_admin=False):
    try:
        cfg = json.dumps(bot_config,ensure_ascii=False,indent=2)
        sys = (ADMIN_SYS if is_admin else USER_SYS).replace("{config}",cfg)
        if uid not in ai_convs: ai_convs[uid]=[]
        msgs = [{"role":"system","content":sys}]+ai_convs[uid][-20:]+[{"role":"user","content":msg}]
        r = groq_client.chat.completions.create(model=GROQ_MODEL,messages=msgs,max_tokens=1000,temperature=0.7)
        reply = r.choices[0].message.content
        ai_convs[uid].append({"role":"user","content":msg})
        ai_convs[uid].append({"role":"assistant","content":reply})
        return reply
    except Exception as e:
        logger.error(f"Groq: {e}"); return "⚠️ خطأ في الذكاء الاصطناعي."

def parse_cmds(text):
    cmds=[]
    for m in re.findall(r'\[\[CMD:(.*?)\]\]',text,re.DOTALL):
        try: cmds.append(json.loads(m.strip()))
        except Exception as e: logger.error(f"CMD parse: {e}")
    clean = re.sub(r'\[\[CMD:.*?\]\]','',text,flags=re.DOTALL).strip()
    return cmds, clean

async def exec_cmd(cmd, context):
    a = cmd.get("action","")
    if a=="broadcast":
        msg=cmd.get("message","")
        if not msg: return "⚠️ لا يوجد نص"
        ok=fail=0
        for uid in list(all_users):
            if uid==ADMIN_ID: continue
            try: await context.bot.send_message(uid,f"📢 إذاعة:\n\n{msg}"); ok+=1
            except: fail+=1
        return f"✅ إذاعة: ناجح {ok} | فاشل {fail}"
    elif a=="add_channel":
        ch=cmd.get("channel","").strip()
        if not ch.startswith("@"): ch="@"+ch
        if ch not in bot_config["extra_channels"] and ch!=bot_config["channel"]:
            bot_config["extra_channels"].append(ch); return f"✅ تمت إضافة القناة: {ch}"
        return f"⚠️ القناة {ch} مضافة مسبقاً"
    elif a=="remove_channel":
        ch=cmd.get("channel","").strip()
        if not ch.startswith("@"): ch="@"+ch
        if ch in bot_config["extra_channels"]:
            bot_config["extra_channels"].remove(ch); return f"✅ تمت إزالة: {ch}"
        return f"⚠️ القناة {ch} غير موجودة"
    elif a=="set_names":
        names=[n for n in cmd.get("names",[]) if n.strip()]
        bot_config["names"].extend(names)
        return f"✅ تمت إضافة {len(names)} اسم | الإجمالي: {len(bot_config['names'])}"
    elif a=="set_password":
        p=cmd.get("password","")
        if p: bot_config["password"]=p; return "✅ تم تعيين الباسورد"
        return "⚠️ فارغ"
    elif a=="set_format":
        f=cmd.get("format","")
        if f: bot_config["format_template"]=f; return "✅ تم تعيين الصيغة"
        return "⚠️ فارغ"
    elif a=="set_prices":
        p=cmd.get("prices","")
        if p: bot_config["prices"]=p; return "✅ تم تعيين الأسعار"
        return "⚠️ فارغ"
    elif a=="set_price_per_gmail":
        try: bot_config["price_per_gmail"]=float(cmd.get("price",0)); return f"✅ سعر الجيميل: {bot_config['price_per_gmail']} ج"
        except: return "⚠️ السعر غير صالح"
    elif a=="clear_names":
        n=len(bot_config["names"]); bot_config["names"]=[]; return f"✅ تم مسح {n} اسم"
    elif a=="ban_user":
        uid=cmd.get("user_id")
        if uid:
            if uid not in db["banned_users"]: db["banned_users"].append(uid); save_db()
            try: await context.bot.send_message(uid,"⛔️ تم حظرك من البوت.")
            except: pass
            return f"✅ تم حظر {uid}"
        return "⚠️ معرف غير صالح"
    elif a=="unban_user":
        uid=cmd.get("user_id")
        if uid and uid in db["banned_users"]:
            db["banned_users"].remove(uid); save_db(); return f"✅ رُفع الحظر عن {uid}"
        return f"⚠️ {uid} غير محظور"
    elif a=="set_welcome":
        m=cmd.get("message","")
        if m: bot_config["welcome_msg"]=m; return "✅ تم تعديل رسالة الترحيب"
        return "⚠️ فارغ"
    elif a=="set_bot_name":
        n=cmd.get("name","")
        if n: bot_config["bot_name"]=n; return f"✅ اسم البوت: {n}"
        return "⚠️ فارغ"
    else: return f"⚠️ أمر غير معروف: {a}"

# ══════════════════════════════════════════════════════
# دوال مساعدة
# ══════════════════════════════════════════════════════
def validate_gmail(email):
    email=email.strip()
    if " " in email: return False,"❌ الجيميل يحتوي على مسافات!"
    if not email.endswith("@gmail.com"): return False,"❌ يجب أن ينتهي بـ @gmail.com"
    if not re.match(r'^[a-zA-Z0-9._%+\-]+@gmail\.com$',email): return False,"❌ صيغة غير صحيحة."
    return True,"✅ الجيميل صحيح."

async def check_subscription(uid, context):
    chs=[bot_config["channel"]]+bot_config.get("extra_channels",[])
    for ch in chs:
        try:
            m=await context.bot.get_chat_member(ch,uid)
            if m.status not in ["member","administrator","creator"]: return False
        except Exception as e: logger.error(f"sub {ch}: {e}")
    return True

async def verify_on_site(email):
    """فحص الجيميل على gmailver.com"""
    try:
        async with httpx.AsyncClient(timeout=15,verify=False) as c:
            r=await c.post("https://gmailver.com/",
                data={"email":email},
                headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                follow_redirects=True)
            txt=r.text.lower()
            if any(w in txt for w in ["valid","exists","found","active","صحيح","موجود"]):
                return True,"✅ الجيميل موجود وفعال (gmailver.com)"
            elif any(w in txt for w in ["invalid","not exist","not found","inactive","غير موجود"]):
                return False,"❌ الجيميل غير موجود أو غير فعال (gmailver.com)"
            return True,"⚠️ تم الفحص على gmailver.com"
    except Exception as e:
        logger.error(f"gmailver: {e}")
        return True,"⚠️ تعذر الاتصال بموقع الفحص"

WALLET_NAMES  = {"vodafone":"فودافون كاش","etisalat":"اتصالات كاش","orange":"أورنج كاش"}
WALLET_EMOJIS = {"vodafone":"📱","etisalat":"📡","orange":"🟠"}

# ══════════════════════════════════════════════════════
# Keyboards
# ══════════════════════════════════════════════════════
def main_kb(uid=None):
    bal = get_balance(uid) if uid else 0
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📬 تسليم الجيميلات",          callback_data="deliver_gmail")],
        [InlineKeyboardButton("📋 الجيميلات المطلوبة اليوم", callback_data="required_gmails")],
        [InlineKeyboardButton("💰 أسعار الجيميلات",          callback_data="prices")],
        [InlineKeyboardButton(f"💳 السحب | رصيدك: {bal} ج",  callback_data="withdraw_menu")],
        [InlineKeyboardButton("👨‍💻 المطور",                   callback_data="developer")],
    ])

def required_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔤 أسماء الجيميلات",  callback_data="names_section")],
        [InlineKeyboardButton("🔑 باسورد الجيميلات", callback_data="password_section")],
        [InlineKeyboardButton("📐 صيغة الجيميلات",   callback_data="format_section")],
        [InlineKeyboardButton("🔙 رجوع",              callback_data="back_main")],
    ])

def names_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 فردي",      callback_data="names_single"),
         InlineKeyboardButton("👥 كل الأسماء",callback_data="names_all")],
        [InlineKeyboardButton("🔙 رجوع",      callback_data="required_gmails")],
    ])

def confirm_gmail_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تأكيد التسليم",callback_data="confirm_deliver")],
        [InlineKeyboardButton("✏️ تعديل",        callback_data="edit_gmail")],
        [InlineKeyboardButton("❌ إلغاء",         callback_data="cancel_deliver")],
    ])

def sub_kb():
    chs=[bot_config["channel"]]+bot_config.get("extra_channels",[])
    btns=[[InlineKeyboardButton(f"📢 اشترك في {c}",url=f"https://t.me/{c.lstrip('@')}")] for c in chs]
    btns.append([InlineKeyboardButton("🔄 تحقق من الاشتراك",callback_data="check_sub")])
    return InlineKeyboardMarkup(btns)

def back_kb(uid=None):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 القائمة الرئيسية",callback_data="back_main")]])

def withdraw_kb(uid):
    u=get_user(uid); bal=u["balance"]; wallets=u.get("wallets",[])
    btns=[]
    if wallets and bal>=MIN_WITHDRAW:
        btns.append([InlineKeyboardButton(f"💸 طلب سحب ({bal} ج)",callback_data="withdraw_request")])
    btns+=[
        [InlineKeyboardButton("📱 فودافون كاش", callback_data="wallet_add_vodafone")],
        [InlineKeyboardButton("📡 اتصالات كاش", callback_data="wallet_add_etisalat")],
        [InlineKeyboardButton("🟠 أورنج كاش",   callback_data="wallet_add_orange")],
        [InlineKeyboardButton("🔙 رجوع",         callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(btns)

def confirm_num_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تأكيد",callback_data="confirm_wallet_num"),
        InlineKeyboardButton("✏️ تعديل",callback_data="edit_wallet_num"),
    ]])

def wallets_kb(wallets):
    btns=[]
    for i,w in enumerate(wallets):
        e=WALLET_EMOJIS.get(w["type"],"💳"); n=WALLET_NAMES.get(w["type"],w["type"])
        btns.append([InlineKeyboardButton(f"{e} {n} - {w['number']}",callback_data=f"wvia_{i}")])
    btns.append([InlineKeyboardButton("🔙 رجوع",callback_data="withdraw_menu")])
    return InlineKeyboardMarkup(btns)

def confirm_wdraw_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تأكيد السحب",callback_data="confirm_wdraw"),
        InlineKeyboardButton("🔙 رجوع",        callback_data="withdraw_menu"),
    ]])

def review_kb(rid):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ قبول",callback_data=f"acc_{rid}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"rej_{rid}"),
    ]])

def wdraw_review_kb(rid):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تأكيد السحب",callback_data=f"wacc_{rid}"),
        InlineKeyboardButton("❌ رفض",         callback_data=f"wrej_{rid}"),
    ]])

def admin_kb():
    total=len(db.get("users",{})); banned=len(db.get("banned_users",[]))
    blocked=len(db.get("blocked_bot",[])); active=total-blocked
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 إضافة أسماء",      callback_data="admin_add_names"),
         InlineKeyboardButton("🔑 الباسورد",          callback_data="admin_set_password")],
        [InlineKeyboardButton("📐 الصيغة",            callback_data="admin_set_format"),
         InlineKeyboardButton("💰 الأسعار",           callback_data="admin_set_prices")],
        [InlineKeyboardButton("💵 سعر الجيميل",       callback_data="admin_set_price_per_gmail")],
        [InlineKeyboardButton(f"👥 المشتركين ({total})",callback_data="admin_subscribers")],
        [InlineKeyboardButton("📊 الجيميلات المسلمة", callback_data="admin_view_delivered")],
        [InlineKeyboardButton("🗑️ مسح الأسماء",       callback_data="admin_clear_names")],
        [InlineKeyboardButton("📢 إدارة القنوات",      callback_data="admin_channels")],
        [InlineKeyboardButton(f"📡 إذاعة ({len(all_users)})", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🤖 تحدث مع AI",        callback_data="admin_chat_ai")],
    ])

def admin_back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 لوحة الأدمن",callback_data="admin_back")]])

def channels_kb():
    chs=[bot_config["channel"]]+bot_config.get("extra_channels",[])
    btns=[]
    for i,ch in enumerate(chs):
        if ch==bot_config["channel"]:
            btns.append([InlineKeyboardButton(f"🔒 {ch} (رئيسية)",callback_data="noop")])
        else:
            btns.append([InlineKeyboardButton(f"➕ {ch} ❌ احذف",callback_data=f"rm_ch_{i}")])
    btns.append([InlineKeyboardButton("➕ إضافة قناة جديدة",callback_data="admin_add_channel")])
    btns.append([InlineKeyboardButton("🔙 رجوع",callback_data="admin_back")])
    return InlineKeyboardMarkup(btns)

def ban_user_kb(target_id):
    if target_id in db.get("banned_users",[]):
        return InlineKeyboardMarkup([[InlineKeyboardButton(f"🔓 رفع الحظر عن {target_id}",callback_data=f"unban_{target_id}")]])
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"🚫 حظر {target_id}",callback_data=f"ban_{target_id}")]])

# ══════════════════════════════════════════════════════
# Handler: Start
# ══════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user=update.effective_user; uid=user.id
    all_users.add(uid)
    u=get_user(uid)
    is_new = u.get("gmails",0)==0 and u.get("balance",0)==0 and u.get("first_name","")==""
    u["first_name"]=user.first_name or ""
    u["username"]=user.username or ""
    save_db()

    if is_banned(uid):
        await update.message.reply_text("⛔️ أنت محظور من استخدام هذا البوت."); return MAIN_MENU

    if uid==ADMIN_ID:
        await update.message.reply_text(
            f"👋 أهلاً يا أدمن!\n🤖 {bot_config['bot_name']} جاهز\n"
            f"👥 المستخدمين: {len(db.get('users',{}))}\n\nاستخدم /admin للوحة التحكم"
        )
        await update.message.reply_text("اختر من القائمة:",reply_markup=main_kb(uid))
        return MAIN_MENU

    subscribed=await check_subscription(uid,context)
    if not subscribed:
        await update.message.reply_text(
            f"⛔️ مرحباً {user.first_name}!\nللاستخدام يجب الاشتراك أولاً 👇",
            reply_markup=sub_kb())
        return MAIN_MENU

    if is_new:
        uname=f"@{user.username}" if user.username else "بدون يوزرنيم"
        mention=f"<a href='tg://user?id={uid}'>{user.first_name}</a>"
        try:
            await context.bot.send_message(ADMIN_ID,
                f"🔔 عضو جديد انضم للبوت!\n\n"
                f"👤 الاسم: {mention}\n"
                f"🆔 الآيدي: <code>{uid}</code>\n"
                f"📛 اليوزر: {uname}\n"
                f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode="HTML")
        except Exception as e: logger.error(f"notify admin: {e}")

    welcome=bot_config.get("welcome_msg","👋 مرحباً {name}!\nاختر ما تريد:").replace("{name}",user.first_name)
    await update.message.reply_text(welcome,reply_markup=main_kb(uid))
    return MAIN_MENU

# ══════════════════════════════════════════════════════
# Handler: check_sub
# ══════════════════════════════════════════════════════
async def check_sub_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    uid=q.from_user.id; all_users.add(uid)
    if await check_subscription(uid,context):
        await q.edit_message_text("✅ تم التحقق! أنت مشترك.\n\nاختر من القائمة:",reply_markup=main_kb(uid))
        return MAIN_MENU
    await q.answer("❌ لم يتم الاشتراك بعد!",show_alert=True)

# ══════════════════════════════════════════════════════
# Handler: القائمة الرئيسية (callback)
# ══════════════════════════════════════════════════════
async def main_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    data=q.data; uid=q.from_user.id
    all_users.add(uid)

    if uid!=ADMIN_ID:
        if is_banned(uid):
            await q.edit_message_text("⛔️ أنت محظور."); return MAIN_MENU
        if not await check_subscription(uid,context):
            await q.edit_message_text("⛔️ يجب الاشتراك أولاً!",reply_markup=sub_kb()); return MAIN_MENU

    # ─── القائمة الرئيسية ───
    if data=="back_main":
        await q.edit_message_text("🏠 القائمة الرئيسية\n\nاختر ما تريد:",reply_markup=main_kb(uid))
        return MAIN_MENU

    elif data=="deliver_gmail":
        await q.edit_message_text(
            "📬 قسم تسليم الجيميلات\n\nأرسل عنوان الجيميل الكامل:\nمثال: john.smith@gmail.com",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع",callback_data="back_main")]]))
        return DELIVER_GMAIL

    elif data=="required_gmails":
        await q.edit_message_text("📋 الجيميلات المطلوبة اليوم\n\nاختر القسم:",reply_markup=required_kb())

    elif data=="prices":
        pr=bot_config.get("prices") or "لم يتم تحديد الأسعار بعد."
        await q.edit_message_text(f"💰 أسعار الجيميلات\n\n{pr}",reply_markup=back_kb())

    elif data=="developer":
        dev=bot_config.get("developer","@T_TSLA")
        await q.edit_message_text(f"👨‍💻 المطور\n\nالبوت مطور بـ Python + Groq AI\nالإصدار: 3.0\nالمطور: {dev}",reply_markup=back_kb())

    # ─── الجيميلات المطلوبة ───
    elif data=="names_section":
        c=len(bot_config["names"])
        if c==0:
            await q.edit_message_text("⚠️ لم يتم تحميل أسماء بعد.",reply_markup=back_kb()); return MAIN_MENU
        await q.edit_message_text(f"🔤 أسماء الجيميلات\n\nعدد الأسماء: {c}\n\nاختر:",reply_markup=names_kb())
    elif data=="names_single":
        if not bot_config["names"]: await q.answer("⚠️ لا أسماء متاحة!",show_alert=True); return MAIN_MENU
        await q.edit_message_text(f"👤 الاسم المخصص لك:\n\n{bot_config['names'][0]}\n\nاستخدمه في إنشاء الجيميل",reply_markup=back_kb())
    elif data=="names_all":
        if not bot_config["names"]: await q.answer("⚠️ لا أسماء متاحة!",show_alert=True); return MAIN_MENU
        txt="\n".join(f"• {n}" for n in bot_config["names"][:50])
        t=len(bot_config["names"])
        if t>50: txt+=f"\n\n... و {t-50} اسم آخر"
        await q.edit_message_text(f"👥 قائمة الأسماء ({t}):\n\n{txt}",reply_markup=back_kb())
    elif data=="password_section":
        p=bot_config.get("password") or "لم يتم تحديد باسورد بعد."
        await q.edit_message_text(f"🔑 باسورد الجيميلات:\n\n{p}",reply_markup=back_kb())
    elif data=="format_section":
        f=bot_config.get("format_template") or "لم يتم تحديد صيغة بعد."
        await q.edit_message_text(f"📐 صيغة الجيميلات:\n\n{f}",reply_markup=back_kb())

    # ─── تأكيد / تعديل / إلغاء التسليم ───
    elif data=="confirm_deliver":
        gmail=pending_gmail.pop(uid,None)
        if not gmail: await q.answer("⚠️ خطأ!",show_alert=True); return MAIN_MENU
        uname=q.from_user.username or "بدون يوزرنيم"
        fname=q.from_user.first_name
        rid=gen_id()
        pending_reviews[rid]={"uid":uid,"gmail":gmail,"username":uname,"first_name":fname}

        # إرسال فوري للأدمن قبل الفحص
        mention=f"<a href='tg://user?id={uid}'>{fname}</a>"
        try:
            await context.bot.send_message(ADMIN_ID,
                f"📧 جيميل جديد في الانتظار (قبل الفحص)\n\n"
                f"📩 {gmail}\n👤 {mention} (@{uname})\n🆔 {uid}",
                parse_mode="HTML")
        except: pass

        await q.edit_message_text(
            f"⏳ تم إرسال الجيميل للأدمن وسيقوم بفحصه في أقرب وقت.\n\n📧 {gmail}",
            reply_markup=back_kb())

        # فحص في الخلفية
        context.application.create_task(_verify_and_notify(rid,gmail,uid,uname,fname,context))
        return MAIN_MENU

    elif data=="edit_gmail":
        pending_gmail.pop(uid,None)
        await q.edit_message_text("✏️ أرسل عنوان الجيميل الجديد:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع",callback_data="back_main")]]))
        return DELIVER_GMAIL

    elif data=="cancel_deliver":
        pending_gmail.pop(uid,None)
        await q.edit_message_text("❌ تم إلغاء التسليم.",reply_markup=back_kb())

    # ─── قبول / رفض الجيميل من الأدمن ───
    elif data.startswith("acc_"):
        rid=data[4:]
        rev=pending_reviews.pop(rid,None)
        if not rev: await q.answer("⚠️ انتهت صلاحية الطلب!",show_alert=True); return MAIN_MENU
        price=float(bot_config.get("price_per_gmail",0))
        add_balance(rev["uid"],price)
        u=get_user(rev["uid"]); u["gmails"]=u.get("gmails",0)+1; save_db()
        await q.edit_message_text(
            f"✅ تم قبول الجيميل!\n\n📧 {rev['gmail']}\n💰 تم إضافة {price} ج لرصيد @{rev['username']}")
        try:
            await context.bot.send_message(rev["uid"],
                f"🎉 تم قبول جيميلك!\n\n📧 {rev['gmail']}\n💰 تمت إضافة {price} ج لرصيدك\n💳 رصيدك الحالي: {get_balance(rev['uid'])} ج")
        except: pass
        try:
            await context.bot.send_message(PROOFS_CHANNEL,
                f"✅ تسليم ناجح!\n\n"
                f"👤 @{rev['username']}\n"
                f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e: logger.error(f"proofs: {e}")

    elif data.startswith("rej_"):
        rid=data[4:]
        rev=pending_reviews.pop(rid,None)
        if not rev: await q.answer("⚠️ انتهت صلاحية الطلب!",show_alert=True); return MAIN_MENU
        await q.edit_message_text(f"❌ تم رفض الجيميل: {rev['gmail']}")
        try:
            await context.bot.send_message(rev["uid"],
                f"❌ للأسف، تم رفض جيميلك.\n\n📧 {rev['gmail']}\n\nيرجى التواصل مع الأدمن لمعرفة السبب.")
        except: pass

    # ─── السحب ───
    elif data=="withdraw_menu":
        bal=get_balance(uid)
        await q.edit_message_text(
            f"💳 قسم السحب\n\n💰 رصيدك الحالي: {bal} ج\n📌 الحد الأدنى للسحب: {MIN_WITHDRAW} ج\n\nاختر محفظتك:",
            reply_markup=withdraw_kb(uid))

    elif data.startswith("wallet_add_"):
        wtype=data[11:]
        context.user_data["wallet_type"]=wtype
        wname=WALLET_NAMES.get(wtype,wtype); emj=WALLET_EMOJIS.get(wtype,"💳")
        await q.edit_message_text(
            f"{emj} إضافة محفظة {wname}\n\nأرسل رقم المحفظة:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع",callback_data="withdraw_menu")]]))
        return WITHDRAW_NUMBER

    elif data=="withdraw_request":
        u=get_user(uid); wallets=u.get("wallets",[])
        if not wallets:
            await q.edit_message_text("⚠️ لم تضف محفظة بعد. أضف محفظة أولاً:",reply_markup=withdraw_kb(uid)); return MAIN_MENU
        await q.edit_message_text(f"💸 طلب سحب\n\n💰 رصيدك: {u['balance']} ج\n\nاختر محفظة السحب:",
            reply_markup=wallets_kb(wallets))

    elif data.startswith("wvia_"):
        idx=int(data[5:]); u=get_user(uid); wallets=u.get("wallets",[])
        if idx>=len(wallets): await q.answer("⚠️ خطأ!",show_alert=True); return MAIN_MENU
        w=wallets[idx]; bal=u["balance"]
        context.user_data["wdraw_wallet_idx"]=idx
        wname=WALLET_NAMES.get(w["type"],w["type"]); emj=WALLET_EMOJIS.get(w["type"],"💳")
        await q.edit_message_text(
            f"💸 تأكيد طلب السحب\n\n"
            f"💰 المبلغ: {bal} ج\n"
            f"{emj} المحفظة: {wname}\n"
            f"📱 الرقم: {w['number']}\n"
            f"👤 الاسم: {w.get('name','')}\n\n"
            f"هل تريد المتابعة؟",
            reply_markup=confirm_wdraw_kb())

    elif data=="confirm_wdraw":
        u=get_user(uid); idx=context.user_data.get("wdraw_wallet_idx",0)
        wallets=u.get("wallets",[]); bal=u["balance"]
        if bal<MIN_WITHDRAW:
            await q.answer(f"⚠️ رصيدك أقل من الحد الأدنى ({MIN_WITHDRAW} ج)!",show_alert=True); return MAIN_MENU
        if idx>=len(wallets): await q.answer("⚠️ خطأ!",show_alert=True); return MAIN_MENU
        w=wallets[idx]; rid=gen_id()
        pending_wdraw[rid]={"uid":uid,"amount":bal,"wallet":w,"username":q.from_user.username or ""}
        wname=WALLET_NAMES.get(w["type"],w["type"]); emj=WALLET_EMOJIS.get(w["type"],"💳")
        fname=q.from_user.first_name; uname=q.from_user.username or "بدون يوزرنيم"
        mention=f"<a href='tg://user?id={uid}'>{fname}</a>"
        try:
            await context.bot.send_message(ADMIN_ID,
                f"💸 طلب سحب جديد!\n\n"
                f"👤 {mention} (@{uname})\n🆔 {uid}\n"
                f"💰 المبلغ: {bal} ج\n{emj} {wname}\n📱 {w['number']}\n👤 {w.get('name','')}",
                parse_mode="HTML",
                reply_markup=wdraw_review_kb(rid))
        except Exception as e: logger.error(f"wdraw notify: {e}")
        await q.edit_message_text(f"✅ تم إرسال طلب السحب للأدمن!\n\n💰 المبلغ: {bal} ج\nسيتم معالجته قريباً.",reply_markup=back_kb())

    elif data.startswith("wacc_"):
        rid=data[5:]; req=pending_wdraw.pop(rid,None)
        if not req: await q.answer("⚠️ انتهت صلاحية الطلب!",show_alert=True); return MAIN_MENU
        u=get_user(req["uid"]); u["balance"]=0; save_db()
        w=req["wallet"]; wname=WALLET_NAMES.get(w["type"],w["type"])
        await q.edit_message_text(f"✅ تم تأكيد السحب!\n\n💰 {req['amount']} ج\n{wname}: {w['number']}")
        try:
            await context.bot.send_message(req["uid"],
                f"✅ تم قبول طلب السحب!\n\n💰 {req['amount']} ج\nعبر: {wname} ({w['number']})\n\nسيتم تحويل المبلغ قريباً.")
        except: pass

    elif data.startswith("wrej_"):
        rid=data[5:]; req=pending_wdraw.pop(rid,None)
        if not req: await q.answer("⚠️ انتهت صلاحية الطلب!",show_alert=True); return MAIN_MENU
        await q.edit_message_text(f"❌ تم رفض طلب السحب.")
        try:
            await context.bot.send_message(req["uid"],f"❌ تم رفض طلب السحب بمبلغ {req['amount']} ج.\nللاستفسار تواصل مع الأدمن.")
        except: pass

    # ─── تأكيد رقم المحفظة ───
    elif data=="confirm_wallet_num":
        num=context.user_data.get("wallet_number","")
        wtype=context.user_data.get("wallet_type","")
        wname=WALLET_NAMES.get(wtype,wtype)
        await q.edit_message_text(f"✅ رقم المحفظة: {num}\n\nأرسل الاسم المسجل في محفظة {wname}:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع",callback_data="withdraw_menu")]]))
        return WITHDRAW_NAME

    elif data=="edit_wallet_num":
        wtype=context.user_data.get("wallet_type","")
        wname=WALLET_NAMES.get(wtype,wtype); emj=WALLET_EMOJIS.get(wtype,"💳")
        await q.edit_message_text(f"{emj} أرسل رقم محفظة {wname} من جديد:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع",callback_data="withdraw_menu")]]))
        return WITHDRAW_NUMBER

    # ─── أدمن: القنوات ───
    elif data.startswith("rm_ch_"):
        idx=int(data[6:]); chs=[bot_config["channel"]]+bot_config.get("extra_channels",[])
        if 0<idx<len(chs):
            ch=chs[idx]; bot_config["extra_channels"].remove(ch)
            await q.edit_message_text(f"✅ تمت إزالة القناة: {ch}",reply_markup=channels_kb())
        else: await q.answer("⚠️ لا يمكن حذف القناة الرئيسية!",show_alert=True)

    elif data.startswith("ban_"):
        target=int(data[4:])
        if target not in db["banned_users"]: db["banned_users"].append(target); save_db()
        try: await context.bot.send_message(target,"⛔️ تم حظرك من البوت.")
        except: pass
        await q.edit_message_text(f"✅ تم حظر المستخدم {target}.",reply_markup=admin_back_kb())

    elif data.startswith("unban_"):
        target=int(data[6:])
        if target in db["banned_users"]: db["banned_users"].remove(target); save_db()
        await q.edit_message_text(f"✅ تم رفع الحظر عن {target}.",reply_markup=admin_back_kb())

    elif data=="noop":
        await q.answer()

    return MAIN_MENU

# ══════════════════════════════════════════════════════
# فحص الجيميل في الخلفية وإرسال النتيجة للأدمن
# ══════════════════════════════════════════════════════
async def _verify_and_notify(rid,gmail,uid,uname,fname,context):
    try:
        # 1. فحص الموقع
        site_ok, site_msg = await verify_on_site(gmail)

        # 2. فحص AI للصيغة
        ai_ok=True; ai_msg=""
        fmt=bot_config.get("format_template","")
        if fmt:
            ai_r=get_ai_resp(uid,f"هل الجيميل '{gmail}' يتوافق مع الصيغة '{fmt}'؟ أجب بـ 'نعم' أو 'لا' فقط مع سبب قصير.")
            ai_ok = any(w in ai_r for w in ["نعم","yes","مقبول","متوافق","صحيح"])
            ai_msg=ai_r[:200]

        mention=f"<a href='tg://user?id={uid}'>{fname}</a>"
        status="✅ مقبول" if (site_ok and ai_ok) else "⚠️ يحتاج مراجعة"
        msg=(
            f"📧 نتيجة فحص الجيميل\n\n"
            f"📩 {gmail}\n"
            f"👤 {mention} (@{uname})\n🆔 {uid}\n\n"
            f"🌐 فحص gmailver.com: {site_msg}\n"
            f"🤖 فحص AI: {'✅ متوافق' if ai_ok else '❌ غير متوافق'}"
        )
        if ai_msg: msg+=f"\n💬 {ai_msg}"
        msg+=f"\n\n{status} - اضغط لاتخاذ القرار:"

        await context.bot.send_message(ADMIN_ID,msg,parse_mode="HTML",reply_markup=review_kb(rid))
    except Exception as e:
        logger.error(f"verify_task: {e}")

# ══════════════════════════════════════════════════════
# Handler: إدخال الجيميل
# ══════════════════════════════════════════════════════
async def recv_gmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; email=update.message.text.strip()
    v,msg=validate_gmail(email)
    if not v:
        await update.message.reply_text(f"{msg}\n\nأرسل الجيميل مرة أخرى.\nمثال: name@gmail.com")
        return DELIVER_GMAIL
    pending_gmail[uid]=email
    await update.message.reply_text(
        f"📧 الجيميل المُدخل:\n{email}\n\nهل هذا هو الجيميل الذي ستسلمه؟ ⚠️",
        reply_markup=confirm_gmail_kb())
    return CONFIRM_GMAIL

# ══════════════════════════════════════════════════════
# Handler: رقم المحفظة
# ══════════════════════════════════════════════════════
async def recv_wallet_num(update: Update, context: ContextTypes.DEFAULT_TYPE):
    num=update.message.text.strip()
    if not re.match(r'^01[0-9]{9}$',num) and not re.match(r'^[0-9]{10,15}$',num):
        await update.message.reply_text("⚠️ رقم غير صالح. أرسل رقم المحفظة الصحيح:")
        return WITHDRAW_NUMBER
    context.user_data["wallet_number"]=num
    wtype=context.user_data.get("wallet_type",""); wname=WALLET_NAMES.get(wtype,wtype)
    await update.message.reply_text(
        f"📱 رقم المحفظة: {num}\n\nهل هذا هو الرقم الصحيح؟",
        reply_markup=confirm_num_kb())
    return WITHDRAW_CONFIRM_NUM

# ══════════════════════════════════════════════════════
# Handler: اسم المحفظة
# ══════════════════════════════════════════════════════
async def recv_wallet_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; name=update.message.text.strip()
    wtype=context.user_data.get("wallet_type","")
    wnum=context.user_data.get("wallet_number","")
    u=get_user(uid)
    # حذف نفس النوع لو موجود
    u["wallets"]=[w for w in u.get("wallets",[]) if w["type"]!=wtype]
    u["wallets"].append({"type":wtype,"number":wnum,"name":name})
    save_db()
    emj=WALLET_EMOJIS.get(wtype,"💳"); wname=WALLET_NAMES.get(wtype,wtype)
    await update.message.reply_text(
        f"✅ تم إضافة طريقة السحب بنجاح!\n\n{emj} {wname}\n📱 {wnum}\n👤 {name}",
        reply_markup=main_kb(uid))
    return MAIN_MENU

# ══════════════════════════════════════════════════════
# Handler: إضافة قناة (أدمن)
# ══════════════════════════════════════════════════════
async def recv_add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID: return MAIN_MENU
    ch=update.message.text.strip()
    if not ch.startswith("@"): ch="@"+ch
    if ch not in bot_config["extra_channels"] and ch!=bot_config["channel"]:
        bot_config["extra_channels"].append(ch)
        await update.message.reply_text(f"✅ تمت إضافة القناة: {ch}",reply_markup=channels_kb())
    else:
        await update.message.reply_text(f"⚠️ القناة {ch} مضافة مسبقاً.",reply_markup=channels_kb())
    return MAIN_MENU

# ══════════════════════════════════════════════════════
# Handler: لوحة الأدمن
# ══════════════════════════════════════════════════════
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID:
        await update.message.reply_text("⛔️ غير مصرح!"); return
    context.user_data["admin_action"]=None
    total=len(db.get("users",{})); banned=len(db.get("banned_users",[]))
    await update.message.reply_text(
        f"👑 لوحة تحكم الأدمن\n\n"
        f"👥 المستخدمين: {total} | 🚫 محظور: {banned}\n"
        f"📧 جيميلات مسلمة: {len(db.get('delivered_gmails',[]))}\n\nاختر:",
        reply_markup=admin_kb())

async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if q.from_user.id!=ADMIN_ID: await q.answer("⛔️ غير مصرح!",show_alert=True); return
    data=q.data

    if data=="admin_back":
        context.user_data["admin_action"]=None
        total=len(db.get("users",{})); banned=len(db.get("banned_users",[]))
        await q.edit_message_text(
            f"👑 لوحة تحكم الأدمن\n\n👥 المستخدمين: {total} | 🚫 محظور: {banned}\n📧 مسلم: {len(db.get('delivered_gmails',[]))}\n\nاختر:",
            reply_markup=admin_kb())

    elif data=="admin_add_names":
        context.user_data["admin_action"]="add_names"
        await q.edit_message_text("📝 أرسل الأسماء (كل اسم في سطر منفصل):",reply_markup=admin_back_kb())

    elif data=="admin_set_password":
        context.user_data["admin_action"]="set_password"
        await q.edit_message_text("🔑 أرسل الباسورد الجديد:",reply_markup=admin_back_kb())

    elif data=="admin_set_format":
        context.user_data["admin_action"]="set_format"
        await q.edit_message_text("📐 أرسل صيغة الجيميلات المطلوبة:",reply_markup=admin_back_kb())

    elif data=="admin_set_prices":
        context.user_data["admin_action"]="set_prices"
        await q.edit_message_text("💰 أرسل جدول الأسعار:",reply_markup=admin_back_kb())

    elif data=="admin_set_price_per_gmail":
        context.user_data["admin_action"]="set_price_per_gmail"
        await q.edit_message_text(
            f"💵 تعيين سعر الجيميل الواحد\n\nالسعر الحالي: {bot_config['price_per_gmail']} ج\n\nأرسل السعر الجديد بالجنيه:",
            reply_markup=admin_back_kb())

    elif data=="admin_view_delivered":
        gmails=db.get("delivered_gmails",[])
        if not gmails:
            await q.edit_message_text("📊 لا توجد جيميلات مسلمة بعد.",reply_markup=admin_back_kb()); return
        txt=f"📊 الجيميلات المسلمة ({len(gmails)}):\n\n"
        for i,g in enumerate(gmails[-20:],1): txt+=f"{i}. {g.get('gmail','')} - @{g.get('username','')}\n"
        await q.edit_message_text(txt,reply_markup=admin_back_kb())

    elif data=="admin_clear_names":
        n=len(bot_config["names"]); bot_config["names"]=[]
        await q.edit_message_text(f"✅ تم مسح {n} اسم.",reply_markup=admin_back_kb())

    elif data=="admin_broadcast":
        context.user_data["admin_action"]="broadcast"
        await q.edit_message_text(
            f"📡 إذاعة للكل\n\n👥 المستخدمين المسجلين: {len(all_users)}\n\nأرسل نص الإذاعة:",
            reply_markup=admin_back_kb())

    elif data=="admin_chat_ai":
        context.user_data["admin_action"]="chat_ai"
        await q.edit_message_text(
            "🤖 محادثة مع AI (Sub-Admin)\n\n"
            "مثال على الأوامر:\n"
            "• 'ابعت إذاعة: مرحباً بالجميع'\n"
            "• 'أضف قناة @ch كاشتراك إجباري'\n"
            "• 'سعر الجيميل 8 جنيه'\n"
            "• 'احظر المستخدم 123456'\n"
            "• 'غير رسالة الترحيب إلى...'\n\n"
            "أرسل /admin للرجوع.",
            reply_markup=admin_back_kb())

    elif data=="admin_channels":
        await q.edit_message_text(
            f"📢 القنوات الإجبارية\n\nالقناة الرئيسية: {bot_config['channel']}\n"
            f"القنوات الإضافية: {len(bot_config['extra_channels'])}\n\nاختر:",
            reply_markup=channels_kb())

    elif data=="admin_add_channel":
        context.user_data["admin_action"]="add_channel_direct"
        await q.edit_message_text("📢 أرسل يوزرنيم القناة الجديدة:\nمثال: @mychannel",
            reply_markup=admin_back_kb())
        return ADD_CHANNEL

    elif data=="admin_subscribers":
        total=len(db.get("users",{}))
        banned=len(db.get("banned_users",[]))
        blocked=len(db.get("blocked_bot",[]))
        active=total-blocked-banned

        txt=f"👥 إحصائيات المشتركين\n\n"
        txt+=f"📊 الإجمالي: {total}\n"
        txt+=f"✅ نشطون: {active}\n"
        txt+=f"🚫 محظورون: {banned}\n"
        txt+=f"❌ حظروا البوت: {blocked}\n\n"
        txt+="─────────────────\n"
        txt+="آخر 10 مستخدمين:\n"
        users=list(db.get("users",{}).items())[-10:]
        for uid_s,u in users:
            uname=u.get("username",""); fname=u.get("first_name","")
            bal=u.get("balance",0)
            star="🚫" if int(uid_s) in db.get("banned_users",[]) else "✅"
            txt+=f"{star} {fname} (@{uname}) | رصيد: {bal} ج | ID: {uid_s}\n"
        txt+="\n💡 لحظر مستخدم أرسل:\n/ban [ID]"
        await q.edit_message_text(txt,reply_markup=admin_back_kb())

    elif data.startswith("rm_ch_") or data.startswith("ban_") or data.startswith("unban_") or data=="noop":
        pass  # تُعالج في main_cb

# ══════════════════════════════════════════════════════
# Handler: رسائل الأدمن
# ══════════════════════════════════════════════════════
async def admin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID:
        return await user_msg(update,context)
    action=context.user_data.get("admin_action")
    txt=update.message.text.strip()

    if action=="broadcast":
        if not all_users:
            await update.message.reply_text("⚠️ لا يوجد مستخدمين."); context.user_data["admin_action"]=None; return
        await update.message.reply_text(f"📡 جارٍ إرسال الإذاعة لـ {len(all_users)} مستخدم...")
        ok=fail=0
        for uid in list(all_users):
            if uid==ADMIN_ID: continue
            try: await context.bot.send_message(uid,f"📢 إذاعة:\n\n{txt}"); ok+=1
            except Exception as e:
                fail+=1
                if "bot was blocked" in str(e).lower():
                    if uid not in db["blocked_bot"]: db["blocked_bot"].append(uid); save_db()
        await update.message.reply_text(f"✅ تمت الإذاعة!\n✅ ناجح: {ok} | ❌ فاشل: {fail}")
        context.user_data["admin_action"]=None

    elif action=="add_names":
        names=[n.strip() for n in txt.split("\n") if n.strip()]
        bot_config["names"].extend(names)
        await update.message.reply_text(f"✅ تمت إضافة {len(names)} اسم!\nالإجمالي: {len(bot_config['names'])}")
        context.user_data["admin_action"]=None

    elif action=="set_password":
        bot_config["password"]=txt
        await update.message.reply_text(f"✅ تم تعيين الباسورد!")
        context.user_data["admin_action"]=None

    elif action=="set_format":
        bot_config["format_template"]=txt
        await update.message.reply_text(f"✅ تم تعيين الصيغة!")
        context.user_data["admin_action"]=None

    elif action=="set_prices":
        bot_config["prices"]=txt
        await update.message.reply_text(f"✅ تم تعيين الأسعار!")
        context.user_data["admin_action"]=None

    elif action=="set_price_per_gmail":
        try:
            bot_config["price_per_gmail"]=float(txt)
            await update.message.reply_text(f"✅ سعر الجيميل: {bot_config['price_per_gmail']} ج")
        except: await update.message.reply_text("⚠️ أرسل رقم صحيح فقط.")
        context.user_data["admin_action"]=None

    elif action=="add_channel_direct":
        ch=txt if txt.startswith("@") else "@"+txt
        if ch not in bot_config["extra_channels"] and ch!=bot_config["channel"]:
            bot_config["extra_channels"].append(ch)
            await update.message.reply_text(f"✅ تمت إضافة القناة: {ch}",reply_markup=channels_kb())
        else:
            await update.message.reply_text(f"⚠️ القناة {ch} مضافة مسبقاً.",reply_markup=channels_kb())
        context.user_data["admin_action"]=None

    else:
        # محادثة AI مع تنفيذ فعلي
        ai_raw=get_ai_resp(ADMIN_ID,txt,is_admin=True)
        cmds,clean=parse_cmds(ai_raw)
        results=[]
        for cmd in cmds:
            r=await exec_cmd(cmd,context)
            results.append(r)
            logger.info(f"AI CMD: {cmd} → {r}")
        parts=[]
        if clean: parts.append(f"🤖 {clean}")
        if results: parts.append("─"*20+"\n⚙️ العمليات المنفذة:\n"+"\n".join(results))
        await update.message.reply_text("\n".join(parts) if parts else "🤖 تم.")

# ══════════════════════════════════════════════════════
# Handler: /ban و /unban
# ══════════════════════════════════════════════════════
async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID: return
    try:
        target=int(context.args[0])
        if target not in db["banned_users"]: db["banned_users"].append(target); save_db()
        try: await context.bot.send_message(target,"⛔️ تم حظرك من البوت.")
        except: pass
        await update.message.reply_text(f"✅ تم حظر {target}.")
    except: await update.message.reply_text("الاستخدام: /ban [user_id]")

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=ADMIN_ID: return
    try:
        target=int(context.args[0])
        if target in db["banned_users"]: db["banned_users"].remove(target); save_db()
        await update.message.reply_text(f"✅ تم رفع الحظر عن {target}.")
    except: await update.message.reply_text("الاستخدام: /unban [user_id]")

# ══════════════════════════════════════════════════════
# Handler: رسائل المستخدمين
# ══════════════════════════════════════════════════════
async def user_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; all_users.add(uid)
    if is_banned(uid): await update.message.reply_text("⛔️ أنت محظور."); return
    if not await check_subscription(uid,context):
        await update.message.reply_text("⛔️ يجب الاشتراك أولاً!",reply_markup=sub_kb()); return
    r=get_ai_resp(uid,update.message.text.strip(),is_admin=False)
    await update.message.reply_text(f"🤖 {r}",reply_markup=back_kb())

# ══════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════
def main():
    print("🚀 تشغيل بوت الجيميلات v3.0 ...")
    print(f"👤 الأدمن: {ADMIN_ID} | 📢 القناة: {CHANNEL_USERNAME}")
    print(f"📊 قناة الإثباتات: {PROOFS_CHANNEL}")
    app=Application.builder().token(BOT_TOKEN).build()

    conv=ConversationHandler(
        entry_points=[CommandHandler("start",start)],
        states={
            MAIN_MENU:[
                CallbackQueryHandler(check_sub_cb,    pattern="^check_sub$"),
                CallbackQueryHandler(admin_cb,         pattern="^admin_"),
                CallbackQueryHandler(main_cb),
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID),admin_msg),
            ],
            DELIVER_GMAIL:[
                MessageHandler(filters.TEXT & ~filters.COMMAND,recv_gmail),
                CallbackQueryHandler(main_cb,pattern="^back_main$"),
            ],
            CONFIRM_GMAIL:[
                CallbackQueryHandler(main_cb),
            ],
            WITHDRAW_NUMBER:[
                MessageHandler(filters.TEXT & ~filters.COMMAND,recv_wallet_num),
                CallbackQueryHandler(main_cb,pattern="^withdraw_menu$"),
            ],
            WITHDRAW_CONFIRM_NUM:[
                CallbackQueryHandler(main_cb,pattern="^(confirm_wallet_num|edit_wallet_num)$"),
            ],
            WITHDRAW_NAME:[
                MessageHandler(filters.TEXT & ~filters.COMMAND,recv_wallet_name),
                CallbackQueryHandler(main_cb,pattern="^withdraw_menu$"),
            ],
            ADD_CHANNEL:[
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID),recv_add_channel),
                CallbackQueryHandler(admin_cb,pattern="^admin_back$"),
            ],
        },
        fallbacks=[CommandHandler("start",start),CommandHandler("admin",admin_panel)],
        per_user=True,per_chat=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("admin",admin_panel))
    app.add_handler(CommandHandler("ban",ban_cmd))
    app.add_handler(CommandHandler("unban",unban_cmd))
    app.add_handler(CallbackQueryHandler(admin_cb,pattern="^admin_"))
    app.add_handler(CallbackQueryHandler(check_sub_cb,pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(main_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID),admin_msg))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,user_msg))

    print("✅ البوت يعمل الآن!")
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    main()
