# Fiscus · 自部署信用卡卡包工作台

卡面墙 · 账单与还款提醒 · 年费管理 · 权益记录。
记录和提醒还款是核心；数据全部保存在本地容器卷，不上传任何第三方。

零预置规则、零推算：不内置任何银行规则，所有数据均为手动录入，
应用只做「每月 X 号」「每年 X 月 X 日」这类通用日历滚动（月末自动夹缩）。

## 功能

- **卡包**：列表 / 卡包双视图；卡面图上传或色块模板；临期卡置顶
- **还款**：按月记账单金额、一键标记已还（当期立即停止提醒）、账单历史
- **年费**：金额、免年费政策、目标笔数与已刷计数、下次年费日
- **权益**：总量 / 已用计数，固定日期失效或周期刷新（每天~每年）
- **提醒**：页内概览条与徽章（逾期红 / 3 天内橙 / 7 天内深）、待办页打卡、每日邮件（SMTP，QQ / 163 / Outlook / Gmail 授权码教程内置）
- **自定义**：应用名、Logo、主题色、背景图、深浅色、登录页
- **安全**：可选密码保护（环境变量）、登录限速、CSP 安全头

## 部署（Docker Compose）

```bash
cp .env.example .env    # 修改 AUTH_PASSWORD
docker compose up -d
```

默认端口 8310，数据目录 `./data`。

Ubuntu / Linux 服务器同理：`curl -fsSL https://get.docker.com | sudo sh` 装好 Docker 后，按上面 Compose 方式启动即可。

## 环境变量

| 变量 | 说明 |
|---|---|
| `AUTH_PASSWORD` | 访问密码，留空 = 关闭鉴权（纯内网可用） |
| `TZ` | 时区，默认 Asia/Shanghai（影响每日邮件扫描时刻） |
| `DATA_DIR` | 数据目录，容器内固定 /data |

## 开发

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

技术栈：FastAPI + SQLite + 原生 JS，与 SubDeck 同构。
