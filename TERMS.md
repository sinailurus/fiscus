# Fiscus 用户协议 / User Agreement

**生效及更新日期 / Effective and last updated: 2026-11-27**（适用 v1.1.0 及之后版本）

## 1. 服务说明 / Service Description

Fiscus 是开源自部署的信用卡卡包工作台，用于记录个人信用卡、账单周期与还款金额，
手动标记已还，并可选提供年费与权益记录、邮箱提醒。所有数据保存在部署者自己的
服务器或 NAS 上，Fiscus 项目方不运营任何云端服务，与任何银行或发卡机构不存在
官方授权、合作或隶属关系；本工具不做任何银行业务推算，还款日与金额以您自行录入
和银行实际账单为准。

Fiscus is a self-hosted credit-card wallet workspace for tracking cards, billing
cycles and payments. All data stays on the deployer's own server or NAS. The
project operator runs no cloud service and is not affiliated with any bank or
card issuer. It performs no banking calculations; due dates and amounts are what
you enter and what your bank statements say.

## 2. 使用条件 / Acceptable Use

用户应在自己拥有或获授权使用的设备与网络环境中部署和使用 Fiscus，不得利用本工具
存储违法内容或用于对外提供记账服务等营利用途（商用授权见第 5 条）。实例暴露公网时，
部署者应设置访问密码并妥善保管服务器凭据；将实例分享给家人朋友使用时，部署者对
实例数据与访问控制负责。

Deploy and use Fiscus only on devices and networks you own or are authorized to
use. Do not store unlawful content or operate it as a paid bookkeeping service
(see §5). When exposing the instance to the public internet, the deployer must
set an access password and safeguard server credentials.

## 3. 数据与备份责任 / Data and Backup Responsibility

所有业务数据保存在部署者指定的 `data/` 目录（SQLite 数据库 + 图片文件）。删除该目录
即物理删除全部数据且无法恢复。备份、迁移与保留期限完全由部署者自行决定与执行；
因未备份、误删、磁盘故障或升级操作不当造成的数据丢失，Fiscus 项目方无法恢复也不承担责任。

升级版本前请阅读对应版本的升级说明，且不要修改 compose 文件中 `volumes` 的映射路径，
否则新容器将读不到旧数据。

All data lives in the deployer-designated `data/` directory; deleting it is
irreversible. Backups, migration and retention are solely the deployer's
responsibility. The Fiscus project cannot recover data lost to missing backups,
misdeletion, disk failure or improper upgrades. Read the upgrade notes before
updating, and never change the `volumes` mapping paths in your compose file.

## 4. 第三方服务 / Third-Party Services

Fiscus 仅在以下场景与第三方发生网络交互，且不发送任何卡片数据：

- **邮箱提醒**（可选）：凭部署者自行配置的 SMTP 信息向邮箱服务商发送提醒邮件。

Fiscus 不接入任何广告、统计或遥测 SDK。详见《隐私政策》（仓库 `static/privacy-policy.html`，
应用内可通过 `/assets/privacy-policy.html` 访问）。

Fiscus talks to third parties only for optional SMTP reminders. No ads, analytics
or telemetry SDKs are included. See the Privacy Policy for details.

## 5. 许可与商用限制 / License and Commercial Use

本项目依据 [PolyForm Noncommercial 1.0.0](LICENSE) 授权：个人学习、自部署与非商用
二次开发可自由使用；任何商用（集成进商业产品、转售、付费托管服务等）需事先获得
作者书面授权。使用本项目即表示接受该许可条款。

The project is licensed under PolyForm Noncommercial 1.0.0: personal,
noncommercial use and modification are free; any commercial use requires prior
written permission from the author. By using the project you accept these terms.

## 6. 免责声明 / Disclaimer

在适用法律允许的最大范围内，软件按"现状"提供，不承诺适用于所有设备、网络环境或
NAS 机型。还款日、金额与提醒均以各发卡机构实际账单为准；因依赖本工具数据导致的
漏还、错还或其他损失，作者不承担责任。

The software is provided "as is", to the fullest extent permitted by law, without
warranty that it will work on every device, NAS model or network environment.
Due dates and amounts are subject to your banks' actual statements; the author is
not liable for missed or incorrect payments based on data in this tool.

## 7. 联系方式 / Contact

源代码、许可证、隐私政策和问题反馈入口位于 GitHub 项目主页：
<https://github.com/sinailurus/fiscus>
