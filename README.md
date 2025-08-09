# Emby Virtual Proxy

本项目是一个功能强大的 **Emby 代理服务器**。它作为中间层部署在您的 Emby 客户端（如浏览器、手机APP）和真实的 Emby 服务器之间。通过智能地拦截和修改客户端与服务器之间的通信数据（API请求），本项目实现了许多 Emby 原生不支持的高级功能，极大地增强了您的媒体库管理和浏览体验。

---

<details>
<summary><strong>点击展开/折叠更新日志</strong></summary>

---

### 🎉 [1.0.0] - 2025-08-09
- **项目首次发布**: 部署 Emby Virtual Proxy 初始版本。
- **核心功能**:
    - 实现虚拟媒体库、高级内容过滤与聚合。
    - 支持为虚拟库自动生成风格化封面。
- **管理后台**: 提供基于 Vue.js 的现代化 Web UI 用于全部功能配置。
- **容器化**: 支持通过 Docker 和 Docker Compose 进行快速、一键式部署。

---

</details>

## 🚀 快速开始 (Docker Compose)

1.  在您的服务器上创建一个目录，例如 `emby-proxy`。
2.  在该目录下，创建一个名为 `docker-compose.yml` 的文件。
3.  将以下内容复制并粘贴到 `docker-compose.yml` 文件中：

    ```yaml
    services:
      # Admin 服务 (管理后台)
      admin:
        image: pipi20xx/emby-virtual-proxy
        container_name: emby-proxy-admin
        command: ["python", "src/main.py", "admin"]
        ports:
          - "8011:8001" # 将管理后台的8001端口映射到主机的8011端口
        volumes:
          - ./config:/app/config # 挂载配置文件目录，确保数据持久化
          - /var/run/docker.sock:/var/run/docker.sock # 挂载Docker sock，允许后台重启代理服务
        restart: unless-stopped
        environment:
          # 这个名字必须和下面 proxy 服务的 container_name 完全一致
          - PROXY_CONTAINER_NAME=emby-proxy-core 

      # Proxy 服务 (代理核心)
      proxy:
        image: pipi20xx/emby-virtual-proxy
        container_name: emby-proxy-core
        command: ["python", "src/main.py", "proxy"]
        ports:
          - "8999:8999" # 代理核心端口
        volumes:
          - ./config:/app/config # 代理服务也需要读取配置
        restart: unless-stopped
        depends_on:
          - admin
    ```

4.  在 `docker-compose.yml` 文件所在的目录中，运行以下命令启动服务：
    ```bash
    docker-compose up -d
    ```

5.  部署成功后：
    - **访问管理后台**: `http://<您的服务器IP>:8011`
    - **在Emby中配置代理**: 将Emby客户端（如Infuse, Emby Web）的服务器地址改为 `http://<您的服务器IP>:8999`

---

## ✨ 核心功能

### 1. 虚拟媒体库 (Virtual Libraries)
- **动态创建**: 您可以创建任意数量的“虚拟媒体库”，这些库并不在 Emby 服务器上真实存在。
- **内容聚合**: 虚拟库的内容可以基于 Emby 中已有的元数据动态生成，支持的源类型包括：
    - **合集 (Collections)**
    - **标签 (Tags)**
    - **类型 (Genres)**
    - **工作室 (Studios)**
    - **演职人员 (Persons)**
- **应用场景**: 轻松创建如 “漫威电影宇宙”、“周星驰作品集”、“豆瓣Top250” 等完全自定义的媒体库，并让它们像真实库一样展示在主页上。

### 2. 高级内容过滤与聚合 (Advanced Filtering & Merging)
- **TMDB ID 合并**: 自动将在不同资料库中但拥有相同 `TheMovieDb.org ID` 的电影或剧集进行聚合。当您在“最近添加”或媒体库视图中浏览时，将只看到一个条目，有效解决版本重复（如 1080p 和 4K 版本）的问题。
- **高级过滤规则**: 提供了一个强大的规则引擎，允许您组合多个复杂的条件来过滤媒体内容，实现 Emby 原生无法做到的精确筛选。

### 3. 自定义封面生成 (Custom Cover Generation)
- **自动化海报**: 可为创建的虚拟媒体库一键生成风格化的海报封面。
- **智能素材抓取**: 该功能会自动从虚拟库中随机选取部分影视项目的现有封面作为素材。
- **高度自定义**: 将抓取的素材智能拼接成一张精美的海报，并允许您添加自定义的中英文标题。

### 4. 现代化Web管理后台 (Modern Web Admin UI)
- **一站式管理**: 项目内置一个基于 Vue.js 和 Element Plus 的美观、易用的网页管理界面。
- **功能全面**: 您可以在此UI上完成所有配置和管理工作，包括：
    - 系统设置（连接 Emby 服务器、API 密钥等）。
    - 创建、编辑、删除虚拟库和高级过滤规则。
    - 通过拖拽调整虚拟库和真实库在 Emby 主页的显示顺序。
    - 手动触发封面生成、清除代理缓存等维护操作。

### 5. 容器化与易于部署 (Docker Ready)
- **开箱即用**: 项目提供完整的 `Dockerfile` 和 `docker-compose.yml` 文件，支持使用 Docker 进行一键部署。
- **服务分离**: 采用双容器架构（代理核心服务 + 管理后台服务），结构清晰，易于维护。
- **API控制**: 管理后台可以通过 Docker API 直接控制代理核心，实现如“重启服务以清空缓存”等高级操作。

---

## 🛠️ 技术架构

## 📱 关于客户端与播放器兼容性

以下为部分播放器（客户端）对 ASS 字体内嵌的支持情况：

| 名称              | 平台                  | 能否正常使用（✅=支持，❌=不支持，？=未知） | 备注                                         |
|-------------------|-----------------------|:------------------:|----------------------------------------------|
| emby web端        | windows/android/linux | ✅                 |     |
| Emby for windows  | windows               | ✅                 |                                              |
| tsukimi           | windows/linux         | ？                 |                                              |
| Emby 小秘书版     | android               | ？                |                   |
| hills             | android               | ？                 |                                              |
| yamby             | android               | ❌                 |无法加载还没解决                                       |
- **后端 (Backend)**:
    - **框架**: Python `FastAPI`
    - **异步处理**: `aiohttp` 用于与 Emby 服务器进行高性能的异步HTTP通信。
    - **缓存**: `cachetools` 用于实现内存缓存，加速API响应。
- **前端 (Frontend)**:
    - **框架/构建**: `Vue.js 3` + `Vite`
    - **状态管理**: `Pinia`
    - **UI 组件库**: `Element Plus`

---

## 🙏 致谢

本项目的设计和功能受到了以下优秀项目的启发，特此感谢：

- **[EkkoG/emby-virtual-lib](https://github.com/EkkoG/emby-virtual-lib)**

---

总而言之，**Emby Virtual Proxy** 是一个为 Emby 高级玩家和收藏家设计的强大工具，它通过“代理”这一巧妙的方式，无侵入性地为您的 Emby 带来了前所未有的灵活性和可定制性。
