# 个性外观

此目录集中管理外观图片、分层骨骼、动作、播放和对话气泡。地图识别不依赖此模块，界面中的「个性外观」开关仍控制是否启用。

## 目录

```text
appearance/
  __init__.py        界面调用入口
  player.py          分层绘制、骨骼变换、动画计时
  speech.py          对话气泡
  events.py          提示内容对应什么动作
  lantern.py         磷焰矿灯的身体：分层、灯光、舞台窗口
  skins/
    doll/            小布偶
      image.png      外观原图
      rig.py         分层轮廓和关节位置
      animation.py   比心、挠头、困倦、招呼的动作角度
      effects.py     手绘符号
      __init__.py    组合此套外观的资源
    lantern/         磷焰矿灯
      image.png      外观原图（444×484）
      rig.py         七层多边形、关节、镜片和亮核位置
      animation.py   各状态的倾斜、提手、链条、晶簇、腿与灯光通道
      effects.py     激光扫射、鬼火、晶簇星光、霜尘、符号
      !.png question.png z.png   冷色版手绘符号（由 doll 的笔触重新上色）
    puppet/          守财木偶
      image.png      外观原图（444×484，来自 BWIKI）
      layers/        预先切好的 12 层（scripts/build_puppet_layers.py 生成）
      sack.png       掉在地上的麻袋
      relics/        辞章图标和 relics.json（名称、品质、价值）
      rig.py animation.py effects.py   关节、动作、音符 / 眼泪 / 晕星
  puppet.py          守财木偶的身体：朝向、麻袋可摘、动作交叉淡入
  heist.py           守财木偶的专属小游戏：偷鼠标
```

`player.py` 的 `RigPlayer` 是两种身体共用的基类（计时、帧缓存、拖动弹簧、淡出、转头）；`PetAnimation` 是布偶，`lantern.LanternAnimation` 是矿灯。`puppet.PuppetAnimation` 是守财木偶。`__init__.py` 的 `SKINS` 列出可选身体，`create_pet(button, 名字)` 创建，`skin_name(settings)` 从设置读取（键 `pet_skin`）。矿灯的激光和鬼火超出按钮范围，画在 `EffectStage` 穿透窗口上，只在动作期间出现。详见 docs/pet-animation.md。

图片在运行时按 rig.py 的多边形拆层，不需要预先导出手臂、头部等 PNG。手臂上下区域合并为完整纹理，沿长度连续弯曲，避免肘部折角。撒娇时双臂向内收一次、停留后放下，不反复摆臂。

## 制作新外观

在 skins 下复制 doll 为新目录，分别调整 image.png、rig.py 和 animation.py。当前播放器采用 306×332 的坐标画布及相同的身体部件命名；替换角色时需要重新调整分层和关节，单换图片不能自动绑骨骼。不同身体结构则需要扩展 player.py。

设置面板「桌宠」一行在小布偶、磷焰矿灯和守财木偶之间切换（`DraggableGear.set_skin`）；默认仍是 doll。新模块必须被代码导入，PyInstaller 才能收集其 Python 代码；skins 下的 PNG/JPG/WebP/JSON 资源会自动加入打包。

docs/images/logo.png 继续作为 README 和项目品牌图片。布偶使用本目录独立的 image.png，以后修改项目 logo 不会意外改动布偶。

## 参考动作

doll/happy.mp4 与 angry.mp4 仅作制作参考，不随便携包打包。撒娇（happy / heart）为 3.6 秒：轻跳、摆腿、躯干摇摆和头部跟随；生气（angry）为 2.2 秒：快速甩臂、交替跺脚和重心抖动。成功提示沿用 heart 事件触发撒娇；普通识别失败触发生气，冲突、中断或异常使用挠头疑惑。播放器以 40 帧/秒更新，同类事件在动作播放期间不重置进度。
