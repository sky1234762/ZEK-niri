<div align="center">

<h1>ZEKniri</h1>

 <a href="https://archlinux.org"><img height="22" src="https://ziadoua.github.io/m3-Markdown-Badges/badges/Arch/arch2.svg" alt="Arch Linux" /></a>
  &nbsp;
  <a href="LICENSE"><img height="22" src="https://ziadoua.github.io/m3-Markdown-Badges/badges/LicenceGPLv3/licencegplv33.svg" alt="GPL-3.0" /></a>
</p>

<p><strong>只是一个辉夜厨子的niri+noctalia桌面</strong><br />
<sub>designed from Niri & noctalia5</sub></p>

![ZEKniri 桌面](preview/desktop-showcase.png)
![ZEKniri 桌面](preview/desktop-showcase2.png)
![ZEKniri 桌面](preview/desktop-showcase3.png)

</div>

## 更改的内容

- **一键切换方案** — 得益于高度友好的waybar,你可以点击调色板模块一键切换预设或soft取色器模式！
- **waybar魔改** — 是的没错，这个waybar有动画！不仅有动画，还能快捷调用你的noctalia设置和命令
- **终端与桌面** — fastfetch独特样式，Kitty 光标轨迹，还有更通透的窗口与物理动画
- **方案同步** — 想要让你的终端和cava跟着模式一起变？点击模块就好了！
- **多款预设和取色器** — 一页一页，这个事没完成的功能，还是等更新罢（无慈悲）

## 配置结构

```
ZEKniri/
├── install.sh               引导入口
├── zekniri/                 引擎（纯标准库，无需pip依赖）
│   ├── core.py             Environment、flock 单实例锁、日志
│   ├── cli.py              命令分发 + 交互面板
│   ├── deploy/             配置替换 · manifest · 模板渲染 · 壁纸
│   ├── state/              快照 · 卸载
│   └── ...
├── configs/                 配置
│   ├── alacritty/          Alacritty 终端
│   ├── cava/               音频可视化
│   ├── fastfetch/          终端信息
│   ├── kitty/              kitty终端
│   ├── niri/               窗口管理器（包含动画和
│   ├── noctalia/           桌面壳与调色模板
│   └── waybar/             状态栏（含 scripts/）
├── assets/wallpapers/       壁纸，部署到 ~/图片/wallpaper
├── logo/title               启动页标题
└── preview/                 演示图
```

## 安装

```bash
git clone https://github.com/sky1234762/ZEK-niri.git ~/ZEKniri
cd ~/ZEKniri
./install.sh              # 交互面板
./install.sh install full # 或直接部署（含依赖检查与壁纸）
```

## 安装完后的界面

![ZEKniri 安装程序](preview/ZEKniri-setup.png)

## attention！
`install.sh` 不能以 root 运行，而且需要 Python 3.11+（用到 `tomllib`）。

安装一次之后，在终端直接输入 **`ZEK-niri`** 就能打开控制面板

- 配置 → `~/.config/<应用>/`
- 壁纸 → `~/pictures/wallpaper/`
- 快照 → `~/.config/ZEKniri/backups/`

## 命令

```
ZEK-niri install [full|config]     部署配置（full = 含依赖与壁纸）
ZEK-niri update [--force|--no-deploy]
ZEK-niri snapshot [备注]           存档当前配置
ZEK-niri rollback [序号]           从存档恢复
ZEK-niri list                      查看所有存档
ZEK-niri deps [core|apps]          安装软件包
ZEK-niri assets                    部署壁纸
ZEK-niri doctor                    自检
ZEK-niri bug                       日志
ZEK-niri uninstall [standard|keep-data|purge]
ZEK-niri test                      沙箱部署（开发者）
```

## 致谢与主页
- QQ：`1846318834` QQ(备用): `3456599262` 
- [bilibili/Zer05ky凌空-ZEK](https://space.bilibili.com/575667990/upload/video) 我的b站主页
- [bilibili/Zer05ky](https://space.bilibili.com/1168962291?spm_id_from=333.1387.follow.user_card.click) 我的直播间
- [SHORiN-KiWATA/shorin-arch-setup](https://github.com/SHORiN-KiWATA/shorin-arch-setup)  waybar配置来源
- [ech678/Nyxniri](https://github.com/ech678/Nyxuri) 安装程序的灵感与借鉴来源
- [KaguyaMao/Tsukuyomi](https://github.com/KaguyaMao/Tsukuyomi) 使用的agent
- bug与问题反馈群号: `1128905094`
- [bilibili/锂琉鉄谷LiSFeDCo](https://space.bilibili.com/1683768632) 可爱吉祥物
