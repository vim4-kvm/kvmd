# PiKVM on VIM4 Ubuntu

`vim4` 分支保留 PiKVM 网页、认证和 API；`KVMD_PLATFORM=vim4` 选择板级差异。
运行于 Ubuntu 24.04，私有 Python 3.14 安装在 `/opt/vim4-pikvm/python`，不替换系统 Python。
构建、打包与部署入口属于 [公共工作区](https://github.com/vim4-kvm/vim4-kvm)。

## 硬件与服务

| 功能 | 接口 |
|---|---|
| 视频 | VIM4 uStreamer：vfmcapsrc → DMA → amlvenc / vim4jpegenc |
| 浏览器视频 | Janus H.264/H.265 WebRTC、H.264/H.265 Direct WebSocket、MJPEG |
| HDMI 声音 | Janus uStreamer 插件，ALSA hw:AMLAUGESOUND,0，48 kHz |
| 键盘、绝对鼠标、相对鼠标 | hidg0、hidg1、hidg2；与板级报告长度匹配，关闭水平滚轮 |
| 本地虚拟介质 | 板级 mass_storage.disk0/lun.0；镜像存储在 /var/lib/kvmd/msd |
| ATX、扩展 GPIO | 未配置，不占用无关 GPIO |

`vim4-pikvm.service` 以 khadas 运行 kvmd、kvmd-media、Janus 与私有 nginx，监听 8080。
任一子进程退出会停止整组。与 NanoKVM、JetKVM、One-KVM 互斥，管理器等待旧应用
退出后再切换。HDMI 服务独立保留 EDID/HPD，观看、刷新、调码率不重新协商 HDMI。
整组进程共享私有 `/dev/shm`，避免普通用户注销时 logind 清除仍在使用的视频共享内存。
uStreamer 及其采集、编码线程限定在 CPU1–7，避开处理网卡与 JPEG 中断的 CPU0。
板上实测 JPEG 线程运行于 CPU0 时会同时出现采集降帧和 UDP 发送缓冲错误；
此限制只作用于视频进程，不改变 Janus、键鼠服务或系统中断的亲和性。
应用不安装或启动树莓派的 OTG、风扇、启动配置或整机更新服务。

启动前，限定助手检查无已挂载介质，保存 USB 链接与 LUN 标志；必要时暂时移除 NCM，
为三个 HID 与一个磁盘保留端点。退出后恢复原始链接和标志。不删除 HID 实例。
挂载镜像逐层拒绝符号链接、路径越界和硬链接，以文件描述符固定 inode，防止重命名替换。
必须先在 USB 主机安全弹出已有虚拟磁盘，再切换应用。切换不自动迁移其他应用的镜像。

## 构建与部署

在完整工作区执行：

```sh
python3 tools/ubuntu-build.py environment --component pikvm
python3 tools/ubuntu-build.py package --component pikvm --version VERSION
python3 tools/ubuntu-build.py verify --component pikvm --version VERSION
python3 tools/board.py deploy --exclusive --packages build/packages/VERSION
```

PiKVM 构建镜像基于已有 `vim4-kvm-builder:ubuntu24.04`。输出 `vim4-pikvm` 与
`vim4-manager` 两个 ARM64 deb、源码与依赖清单和校验和；复用已安装的板级和编码包。
安装保留原应用选择，不自动启用 PiKVM；在管理器中选择 PiKVM 后打开 8080。
首次使用上游默认网页账户 admin/admin；通过 `kvmd-htpasswd` 管理其独立密码文件，
不改变 Ubuntu 账户。升级保留 htpasswd、TOTP 和 override.yaml。

验证包括 Janus 插件实际挂载/卸载、服务配置和动态库解析；软件通过不代表上板通过。
硬件证据见公共工作区 `docs/bringup-log.md`。

Direct 播放在解码积压达到三帧时停止接受新输入，允许已有解码任务完成后请求关键帧，
等待新关键帧后恢复，避免反复取消慢解码任务导致一直没有画面；
服务端发送队列溢出也会丢弃旧 GOP 的后续依赖帧。此策略保留分辨率与码率，
慢客户端会短暂等待关键帧，而不是持续播放积压画面。它不能消除 TCP 内部已缓存的数据。

视频切换回归在构建环境运行 `python3 -m unittest discover -s deploy/vim4 -p 'test_*.py'`；
HEVC SPS 解析和 Direct 绘制生命周期运行
`node --test deploy/vim4/test_stream_hevc.mjs deploy/vim4/test_direct_render.mjs`。
`node deploy/vim4/test_direct_browser.mjs /path/to/recording.h265` 使用以关键帧开头的
Annex B 录像，在本机 Chrome 验证真实 Direct 解码、重连和菜单切换，不访问板子。
需要 Playwright（可通过 `PLAYWRIGHT_MODULE` 指定已有模块路径）和 Chrome。

## 边界

当前输出尺寸跟随 HDMI 输入，视频帧率可限制，H.264 码率范围 1000–60000 kbps。
默认 H.264，关键帧间隔 30 帧。网页 Video mode 提供 WebRTC H.264、Direct H.264、
WebRTC H.265、Direct H.265 和 MJPEG。H.265 分别要求浏览器支持 HEVC WebRTC 或
HEVC WebCodecs；Direct 使用 HTTPS（或 localhost 安全上下文），两种 Direct 均不传音频。
所有观看者共用编码器：切换 H.264/H.265 会重启采集编码、Janus 和 media 服务，
所有观看者短暂重连；认证、键鼠和虚拟介质服务保持运行。其他观看者跟随当前编码，
保留各自的 WebRTC/Direct/MJPEG 传输选择，不会因刷新页面覆盖共享编码。
选择保存在 `/var/lib/kvmd/video-codec`，优先于 `/etc/default/vim4-pikvm` 的
`VIM4_VIDEO_CODEC` 启动默认值；删除该状态文件后重启服务可恢复启动默认值。
Direct H.265 从关键帧 SPS 读取解码 profile/level，并等待包含参数集的关键帧开始播放。
Direct 在每次显示刷新时绘制最新已解码帧，释放同一刷新周期内被替代的旧帧；
编码帧仍按顺序解码，避免破坏帧间依赖。这减少突发到达时显示陈旧画面的延迟。
Direct 视频 WebSocket 不协商 permessage-deflate：视频已由编码器压缩，再压缩大关键帧
会延迟发送并积压后续帧，表现为周期性卡顿；控制通道保持原有压缩设置。
EDID/HDR 使用已有板级工具与管理器。2026-10-15 的 `.50` 包已实板验证四种视频模式的
4K 解码、编码切换和刷新重连；Direct 通过 localhost SSH 转发验证。未覆盖长时间运行、
运动画面端到端延迟及所有浏览器，证据见公共工作区 `docs/bringup-log.md`。
Janus 使用 regular ICE nomination，保留 IPv4/IPv6。双网卡客户端上 aggressive
nomination 曾将视频发往 Wi-Fi IPv6，而浏览器统计报告有线 IPv4；定位网络卡顿时
需要核对实际收包接口，不能仅凭网页地址或 selected candidate pair 判断视频路径。
本地镜像上传、下载与挂载使用原生业务；远端 NBD 直连、USB 麦克风、USB 网卡管理、
树莓派整机更新与可选扩展服务不在本次板级集成中，不能通过上游固件更新 VIM4。
