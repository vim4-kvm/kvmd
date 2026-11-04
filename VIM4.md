# PiKVM on VIM4 Ubuntu

本页管 PiKVM 的板级生命周期、共享介质与浏览器视频边界。
当前重点：公共网关认证，平台组件先于应用升级，视频重建须保留 HID。
按需读：[服务与介质](#服务与介质)、[视频](#视频与浏览器)、[构建](#构建与验证)。
参数、路径、默认值以链接的配置和源码为准；历史通过不代表当前上板通过。

## 服务与介质

平台入口保留原生网页与 API，使用私有 Python，不替换系统解释器。
[启动器](deploy/vim4/vim4-pikvm-run)协调持久组件与视频组件：
子进程异常退出停止整组，编码切换只重建视频组，认证、HID 与介质服务继续运行。
[服务配置](deploy/vim4/vim4-pikvm.service)提供私有共享内存，避免用户注销时被 logind 清理。
视频线程避开网卡/JPEG 中断所在 CPU；此前线程争用同时导致采集降帧和 UDP 缓冲错误。
此限制不能推及 Janus、HID 或系统中断。

公共启动器按内核选择后端，保留账户和数据；主线音频配置在运行目录生成，
不覆盖厂商内核的持久配置。应用经管理器统一登录，
[nginx](deploy/vim4/nginx.conf)与[应用配置](deploy/vim4/override.yaml)
维护入口，不使用上游账户页面。升级修改 YAML 应保留其余设置、注释与认证数据；
主 override 优先于片段，不能用片段覆盖旧的认证开关。
ATX/扩展 GPIO 未接线，不占无关 GPIO；不安装树莓派 OTG、风扇或整机更新服务。

启动前 [限定介质助手](deploy/vim4/vim4-pikvm-media)拒绝已挂载介质，保存 USB 链接与 LUN 标志，
必要时释放网卡端点，退出恢复。不得删除 HID 实例。
先在 USB 主机安全弹出，再切应用；不自动迁移其他应用的挂载。
目录逐级拒绝链接、越界及硬链接，固定 inode 防止重命名替换；
共享目录读取、双锁与编辑锁遵循公共
[vim4media](https://github.com/vim4-kvm/vim4-kvm/blob/main/board/vim4media.py)。
其他来源镜像与共享盘只读，不允许删除覆盖，ISO 强制光盘。
本应用挂载的目录外镜像可弹出，他处挂载的仍显示为外部介质；
目录刷新不能绕过启动时占用检查。

## 视频与浏览器

菜单、持久选择和输出高度见 [vim4video](kvmd/vim4video.py)，
后端路由见公共[音视频说明](https://github.com/vim4-kvm/vim4-kvm/blob/main/docs/subsystems/video.md)。
所有观看者共享编码器，切编码会重启视频组件并短暂重连；
其他观看者保留传输偏好，不因刷新覆盖共享编码。
尺寸只缩小、不放大；厂商 SDR 用 GE2D，HDR 用 Mali/P010，JPEG 保留独立路径。
主线 JPEG 跟随采集缩小；此新增入口仍待上板。
先部署匹配的启动器、采集、编码与私有标准 V4L2 插件；
厂商替代插件会关闭主 RX，不可混用。HDMI 服务独立，观看与调码率不重新协商输入。

HEVC 原生 PQ 跟随管理器全局偏好，SDR 不增加十位转换；
Janus 按实际能力协商，Direct 从 SPS 选择解码器并等含参数集的关键帧。
普通 Canvas 是兼容 SDR 路径，Safari 真 HDR 未验收。
Direct 依赖浏览器相应解码能力与安全上下文，不传音频。
[Direct 实现](web/share/js/kvm/stream_media.js)让已提交解码完成后再请求关键帧，
避免反复取消慢解码导致永远无画面；服务端溢出丢旧 GOP 依赖帧。
显示刷新只画最新已解码帧，但编码帧仍须顺序解码，不能破坏参考链。
这不能消除 TCP 内部积压。视频 WebSocket 禁用重复压缩，
否则大关键帧会被再次压缩而延迟后续帧。

Janus 保留双栈，使用 regular nomination。双网卡曾出现统计所选候选与实际视频收包接口不符，
排查须核对实际接口，不能只看网页地址或 selected candidate pair。
远端 NBD、USB 麦克风/网卡管理、树莓派更新与可选扩展不属此次集成。
历史多模式验收见
[上板索引](https://github.com/vim4-kvm/vim4-kvm/blob/main/docs/bringup/README.md)；
长期运行、运动端到端延迟和全部浏览器仍未覆盖。

## 构建与验证

完整工作区用 [构建工具](https://github.com/vim4-kvm/vim4-kvm/blob/main/tools/ubuntu-build.py)
的 environment、package、verify 流程，再用部署工具安装。参数以工具帮助为准。
复用平台包，安装保留原应用选择；切至 PiKVM 后使用管理器账户，不更改 Ubuntu 账户。
软件核验须包含 Janus 实际挂卸载、服务配置与动态库解析。

子仓库离线回归：
```sh
python3 -m unittest discover -s deploy/vim4 -p 'test_*.py'
node --test deploy/vim4/test_stream_hevc.mjs deploy/vim4/test_direct_render.mjs
```
真实浏览器 Direct 回归见 [浏览器测试](deploy/vim4/test_direct_browser.mjs)头部与参数：
使用从关键帧开始的 Annex B 录像、本机 Chrome 与 Playwright，不访问板子。
离线通过不能替代实际 USB 枚举、GPU、HDR 或浏览器硬件验收。
