# 个性外观

此目录集中管理外观图片、分层骨骼、动作、播放和对话气泡。地图识别不依赖此模块，界面中的「个性外观」开关仍控制是否启用。

## 目录

```text
appearance/
  __init__.py        界面调用入口
  player.py          分层绘制、骨骼变换、动画计时
  speech.py          对话气泡
  events.py          提示内容对应什么动作
  skins/
    doll/            当前布偶外观
      image.png      外观原图
      rig.py         分层轮廓和关节位置
      animation.py   比心、挠头、困倦、招呼的动作角度
      __init__.py    组合此套外观的资源
```

图片在运行时按 rig.py 的多边形拆层，不需要预先导出手臂、头部等 PNG。手臂采用肩膀带动肘部的父子变换。

## 制作新外观

在 skins 下复制 doll 为新目录，分别调整 image.png、rig.py 和 animation.py。当前播放器采用 306×332 的坐标画布及相同的身体部件命名；替换角色时需要重新调整分层和关节，单换图片不能自动绑骨骼。不同身体结构则需要扩展 player.py。

代码中通过 PetAnimation(button, skin=新外观模块) 指定外观；当前仍默认使用 doll，尚未增加界面中的多外观选择器。新模块必须被代码导入，PyInstaller 才能收集其 Python 代码；skins 下的 PNG/JPG/WebP/JSON 资源会自动加入打包。

docs/images/logo.png 继续作为 README 和项目品牌图片。布偶使用本目录独立的 image.png，以后修改项目 logo 不会意外改动布偶。

## 参考动作

doll/happy.mp4 与 angry.mp4 仅作制作参考，不随便携包打包。撒娇（happy / heart）为 3.6 秒：轻跳、摆腿、躯干摇摆和头部跟随；生气（angry）为 2.2 秒：快速甩臂、交替跺脚和重心抖动。成功提示沿用 heart 事件触发撒娇，冲突、中断或异常触发生气，普通识别失败仍使用挠头。播放器以 40 帧/秒更新，同类事件在动作播放期间不重置进度。
