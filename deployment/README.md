# 部署说明

本目录包含将调度器部署为系统服务的配置文件。

## 文件说明

### Linux (systemd)
- **文件**: `crawler-refinery.service`
- **用途**: systemd 单元文件，用于将调度器注册为 Linux 系统服务

### macOS (launchd)
- **文件**: `com.chz.crawler-refinery.plist`
- **用途**: launchd plist 文件，用于将调度器注册为 macOS 系统服务

## 使用前准备

1. 根据你的系统选择对应的配置文件
2. 修改文件中的以下路径：
   - Python 解释器路径（使用 `which python3` 查看）
   - 项目工作目录路径
   - 用户名/组名（Linux）
3. 确保 `.env` 文件已配置正确
4. 确保 `config.yaml` 中的调度任务已配置

## 部署步骤

详细的部署步骤请参考项目根目录的 `README.md` 中的"定时调度服务 > 生产部署"章节。

## 注意事项

- 部署前建议先在前台运行 `python scheduler.py` 测试是否正常
- 确保日志目录 `logs/` 具有写入权限
- systemd 服务会在失败时自动重启（RestartSec=10）
- launchd 服务会在崩溃时自动重启（KeepAlive=true）
