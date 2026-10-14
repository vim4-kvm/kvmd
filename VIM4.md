# PiKVM on VIM4 Ubuntu

`vim4` 分支保留 PiKVM 网页、认证和 API；`KVMD_PLATFORM=vim4` 选择板级差异。
运行于 Ubuntu 24.04，私有 Python 3.14 安装在 `/opt/vim4-pikvm/python`，不替换系统 Python。
构建、打包与部署入口属于 [公共工作区](https://github.com/vim4-kvm/vim4-kvm)。

## 硬件与服务

| 功能 | 接口 |
|---|---|
| 视频 | VIM4 uStreamer：vfmcapsrc → DMA → amlvenc / vim4jpegenc |
| 浏览器视频 | Janus H.264 WebRTC、原生 H.264 media WebSocket、MJPEG |
| HDMI 声音 | Janus uStreamer 插件，ALSA hw:AMLAUGESOUND,0，48 kHz |
| 键盘、绝对鼠标、相对鼠标 | hidg0、hidg1、hidg2；与板级报告长度匹配，关闭水平滚轮 |
| 本地虚拟介质 | 板级 mass_storage.disk0/lun.0；镜像存储在 /var/lib/kvmd/msd |
| ATX、扩展 GPIO | 未配置，不占用无关 GPIO |

`vim4-pikvm.service` 以 khadas 运行 kvmd、kvmd-media、Janus 与私有 nginx，监听 8080。
任一子进程退出会停止整组。与 NanoKVM、JetKVM、One-KVM 互斥，管理器等待旧应用
退出后再切换。HDMI 服务独立保留 EDID/HPD，观看、刷新、调码率不重新协商 HDMI。
整组进程共享私有 `/dev/shm`，避免普通用户注销时 logind 清除仍在使用的视频共享内存。
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

## 边界

当前输出尺寸跟随 HDMI 输入，视频帧率可限制，H.264 码率范围 1000–60000 kbps。
H.265 未接入 PiKVM 的视频接口。EDID/HDR 使用已有板级工具与管理器。
本地镜像上传、下载与挂载使用原生业务；远端 NBD 直连、USB 麦克风、USB 网卡管理、
树莓派整机更新与可选扩展服务不在本次板级集成中，不能通过上游固件更新 VIM4。
