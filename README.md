# Random Media Forward Bot

Source channel se random media (naya media pehle) target channel me **bina forward tag** ke bhejta hai.

## Environment variables (Render me daalo)
| Name | Kaha se |
|---|---|
| `API_ID`, `API_HASH` | my.telegram.org |
| `BOT_TOKEN` | @BotFather |
| `OWNER_ID` | Aapka Telegram user ID (@userinfobot se) |
| `DATABASE_URI` | MongoDB Atlas connection string |
| `DATABASE_NAME` | optional (default: randomforwardbot) |

`PORT` aur `RENDER_EXTERNAL_URL` Render khud set karta hai.

## Render deploy
1. Ye saari files GitHub repo me daalo.
2. Render > New > **Web Service** > repo connect > Language: **Docker**.
3. Upar ke environment variables add karo > Deploy.
4. **Sleep rokne ke liye:** bot khud har 5 min apne URL ko ping karta hai. Backup ke liye uptimerobot.com pe free monitor banao (HTTP, 5 min) apne Render URL ke liye.

## Channel setup
- Bot ko **source** aur **target** dono me admin banao (target me post permission).
- Source me "Restrict saving content" OFF hona chahiye, warna copy nahi hoga.

## Commands (sirf owner)
```
/setsource -1001234567890      (ya @username)
/settarget -1009876543210
/setlast https://t.me/c/1234567890/20000   (source ki last post ka link)
/setinterval 10m | 1h | 2h
/setcount 5
/startpost   /stoppost   /postnow   /status   /resetsent
```
