# 模型包

一个模型一个文件夹，`packs/<id>/pack.json` 写清这个模型的一切。加模型只加文件夹，不改代码；声音绑在模型上，不共用。读包的代码在 `widget/packs.py`。现在有 `border_collie`（边牧，默认）、`samoyed`（萨摩耶）、`ball`（球）和十一个物件的包（狗窝、盆、公园里的东西，见下面「物件的包」）。声音来源看 `CREDITS.md`。

## 加一个模型
1. 新建 `packs/<id>/`，模型放进去，或者放在 `models/`（购买的内容不入 git）。
2. 写 `pack.json`（照着 `border_collie/pack.json` 抄）。
3. 量 `gaits`（片段本来的速度）、`height_m`、`fit_m`：`python tools/measure_pack.py <id> --ref border_collie`（量法在文件开头）；Bark 片段嘴开合的时刻也在里面，对着它定 `clip_sounds` 的 `at`；`mouth_offset`、`head_shot`、`jumps` 的建议值也在里面（出图看过再定）。
4. 出缩略图 `python tools/render_pack_thumb.py <id>`；看样子 `python tools/render_still.py --pack <id> --coat 2 --clip Idle_1 --out x.png`。
5. 跑 `python -m unittest tests.test_packs`（`SecondModelTests` 就是用一个假模型这样跑一遍）。

`kind: "pet"` 的包多于一个，添加同桌页就能选（一只同桌的模型在添加时定；换到别的模型的同桌当场换、不重启，模型在后台先读好）。模型文件不在的包不列出来（购买的模型不入 git）。

## pack.json 里有什么
| 键 | 是什么 |
|---|---|
| `id`、`kind` | 名字；`pet`（能选的模型）或 `prop`（球、物件） |
| `name` | 显示的名字，`{"en": …, "zh": …}` |
| `default_name` | 没起过名字时叫什么 |
| `species`、`icon` | 什么动物（不写是 dog）；名字胶囊里名字左边的物种图标：内置 `bone` 或包里一张图；不写按物种取（狗 = 骨头） |
| `model` | 模型文件。先找包的文件夹，再找程序根目录 |
| `thumb` | 添加同桌页的缩略图，由 `tools/render_pack_thumb.py <id>` 画 |
| `coat_dir`、`coats`、`custom_coat` | 毛色贴图（几个模型放同一个文件夹，文件名别撞）；能不能自定义毛色（做法是给深浅两色的毛定的；false：设置卡片不出「自定义」，自定义毛色页打不开） |
| `coat_custom` | 自定义毛色怎么分：`mode`（不写 = 按深浅分两色；`tint` = 整身一个色 + 可选「背上一片」，萨摩耶）、`patch_from`（背上那一片取自第几套贴图里偏黄的地方）、`default`（第一次自定义、重置用的主色 / 副色 / 斑纹）、`patterns`（每种斑纹的 `name`、`note`）、`common_colors`（自定义页的常用颜色，[主色, 副色] 一对一对；不写用 `coat.COMMON_COLORS`） |
| `coat_notes` | 每套毛色一项：`name`（头像下面的名字）、`pattern`（自定义页那张斑纹图下面的一句），各写 `en`、`zh`；不写就显示编号 |
| `brightness` | 贴图整体提亮多少倍（不写是 1）。照着打了光来画的贴图在三渲二下偏灰：萨摩耶 1.4；用 `tools/render_still.py --brightness` 试 |
| `height_m`、`fit_m`、`mass_kg` | 站着多高（站着的片段里最高的关节 + 耳朵 0.11，当身子的尺度用：圈多大、跳多高、推荐大小）；窗口上沿离屏幕顶至少多高才站得下（再 + 0.06）；质量 |
| `mouth_offset` | 叼着的东西相对头骨放哪（头骨局部，米：前、上是第二、三个数）；不写用边牧的（`props.MOUTH_OFFSET`），头大的按比例放大 |
| `head_shot` | 毛色那一行的头像怎么取景：`clip`（哪段片段的第一帧）、`tall_m`（画面多高）、`at`（头骨在画面里多高）；不写的用 `look.py` 的（站着、0.30、0.42） |
| `jumps` | 整段片段的跳法腾空的那段进度按这个模型改：`{"hop": {"arc": [起, 止]}}`（同名片段长短不一样时；`clips.jumps_for`） |
| `gaits` | 走、小跑、跑、快跑、倒着走的片段本来多快（米 / 秒） |
| `clips` | 代码认的片段名 → 这个模型里的片段名。一样的不用写 |
| `bones` | 代码认的骨头名 → 这个模型里的骨头名。一样的不用写 |
| `sounds` | 声音事件 → 文件。可以写 `min_gap`（两次至少隔多久）、`volume`（音量跟哪一项） |
| `clip_sounds` | 片段播到第几秒响（`at`）、每隔几秒响（`every`、`first`）、长声音片段换了就停（`hold`）；键写成「动作:片段」（如 `bow_bark:Idle_5_loop`）的只在做这个动作时响；`fade_in` 每一下从 0 拉上来几秒、`fade_out` 长声音停时淡掉几秒（吃 0.4 / 0.5、喝每下 0.08） |
| `action_sounds` | 同上，绑在动作上（`clips.py` 的动作 id） |
| `tuning` | 调参项的默认值（表在 `widget/tuning.py`；开发者设置页「复制数值」的结果贴进来，质量写在 `mass_kg`） |

代码认的片段名、骨头名就是边牧的（`Run_F_IP`、`head`、`foot_b.L`……，萨摩耶同名），`widget/clips.py`、`widget/roam.py` 用的就是这些。

## 物件的包
一类物件一个包（`kind: "prop"`），多一段 `thing`；几款样子写在 `thing.styles` 里，每一款能盖掉 `thing` 里的任何一项。
加一款：模型放 `models/props/`（`tools/export_things.py` 导，买来的不入 git）→ `styles` 里加一段 → `python tools/render_thing_thumbs.py <包>` 出缩略图 → `python tools/render_still.py --thing <包>/<款> --out x.png` 看样子 → `python -m unittest tests.test_thing_art`。

| `thing` 里的键 | 是什么 |
|---|---|
| `group`、`order` | 「物件」页分在哪组（`rest` 窝 / `food` 吃喝 / `toys` 玩具 / `park` 公园）；组里的先后 |
| `role` | 怎么用：`bed` 窝 / `house` 屋 / `bowl` 盆 / `fetch` 叼的玩具 / `push` 顶的玩具 / `hurdle` 栏 / `decor` 摆设。代码只认它；「物件」页只列有用法的三种（`bed`、`house`、`bowl`，`things.SUPPORTED_ROLES`），别的包写着、留着，不列 |
| `scale`、`fit_pet` | 放大多少倍；`fit_pet`：再乘现在这只狗的身高比（`height_m` ÷ 0.8，狗窝） |
| `yaw`、`mirror` | 朝哪个角度画（度）；`mirror`：在屏幕右半边按 −yaw 画（尖顶狗屋，门朝屏幕中间） |
| `shadow` | 脚下画不画影子（玩具写 false：球的影子是球的小窗口自己画的） |
| `rest`、`front_z` | 窝：狗歇在哪 `{"x", "rise", "side", "half"}`（米，模型单位，用的时候乘倍数；`side` 0 歇在物件正中偏 `x` 的地方，`rise` 垫子多高、狗的根抬到那（0 = 不抬，趴在它前面的地上：平顶狗屋门前），`half` 垫子横着的半宽（狗跑、走经过时身子正中在这个范围里就踩在垫子上；量模型里两边边沿以内的那一段，不写按画出来宽度的 0.7）；`side` 1 歇在门朝的那一侧外面、头朝外，`x` 是离那条边再留多远（米，不乘倍数；狗的身长程序自己按模型量）；比 `front_z` 更靠镜头的面另画一层盖在狗前面 |
| `platform` | 台子（列出来的只有平顶狗屋；长椅、跷跷板、独木桥的包也写着）：`{"y", "x0", "x1", "thick"}` 上沿多高、左右到哪（转过角度以后画面上的）、往下多厚（米，模型单位）；`thick` 不比 `y` 小 = 实心盒子（球滚不过去），小 = 薄板（球能从底下过） |
| `serves` | 盆：`food` / `water`（写了才是能吃的盆：点一下叫狗来吃 / 喝，吃完换成 `model_empty` 的样子） |
| `physics` | 扔出去、落地的样子（`things.ThingPhysics`；开发者设置页里能调，「复制数值」出的就是这一段；不写按默认）：`mass_kg` 质量（越重出手越慢、飞得越近）、`bounce` 落地弹回几成、`friction` 落地以后滑的时候每秒慢多少（米 / 秒²）、`squash` 落地最重时压扁几成、`recover` 弹回来多快（弹簧的倍数，小于 0.8 的不弹过头、慢慢鼓回来）、`dust` 扬灰多少（0 不扬）、`shake` 震旁边的东西多重（0 不震）、`sound` 落地那一声（包里的文件，只在人扔、拖着放下时响）、`volume` 那一声多响 |
| `hurdle` | 栏：`{"h"}` 多高（只有矮栏写，写了狗才跳） |
| `draw`、`carry`、`tint`、`radius` | 玩具：`draw: "ball"` 是程序自己画的红球（没有模型）；`carry` 狗嘴里用 `props.py` 的哪个（`ball` / `bone`，不写 = 叼不动）；`tint` 嘴里那个涂什么色；`radius` 算物理的半径（米，画出来的大小）。玩具的物理写在包的 `tuning`、`mass_kg`，声音各包自带 |
| `styles` | 每款 `{"id", "name": {"en", "zh"}, "model", "model_empty"（空盆）, "thumb"（不写是 `thumb-<id>.png`）}`，加上要盖掉的键 |

`rest`、`front_z`（窝）、`serves`（盆）、`platform`（台子）、`physics`（扔、落地）接了；`hurdle`、玩具那几项现在只是写着。列在「物件」页、摆得出来的只有 `things.SUPPORTED_ROLES` 里的角色（窝、屋、盆）；摆设、栏、玩具的包留着，做了用法再把角色加回去。英文名别超过 12 个字母（格子 86 宽，再长就省略）。

## 缺东西会怎样
- 物件的模型文件不在：那一款不列出来（`packs.things`）；`group`、`role` 写错的跳过。
- 缺片段：按 `packs.CLIP_FALLBACK` 找替代（没有快跑用跑），最后落到站着待机；要等这段片段的地方直接跳过。
- 没有 `Pick_up`：狗跑到球旁边就算了，不叼。
- 缺骨头：没有嘴就不动嘴；没有尾巴不摇；拎起来的姿势里缺的部分不动。
- 缺声音：不响。
- 缺得太多（没有 `head`、`Spine_base`、`foot_*`、`Idle_1`）：用不了，回到默认那只（`packs.problems`）。

## 还写死在代码里的
球的大小、颜色在 `widget/props.py`（`BALL_R`、`COLORS`）。球的包里已经写了几款网球（`thing.styles`），接进来以前现在这只红球还照写死的画。
