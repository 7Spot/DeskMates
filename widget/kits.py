"""换到别的模型的同桌不重启：每个模型一份「备好的东西」（Kit），
别的模型由后台线程先备好，滑到位时窗口只换引用（window._use_kit，主线程 1.5～3.0 毫秒，离屏量的）。

- Kit：包、模型（apply_names 过的）、调参（Tuning）、声音（SoundBank）；按模型量一次的东西记在模型上（gltf.Model.measured：片段最高点、脚和骨盆、
  趴着的身长、拎起来的姿势、跳法的数、鼻子最低那一刻、渲染器的顶点表和描边表）。
- Kits：adopt（启动时那只，窗口自己建的）、want（还没有就开始备，后台一次一件）、get（等到有；读不出来 None）、forget（名单里没有哪只再用这个模型了才丢）。
- 后台那件活（_prepare）：读模型（packs.load_model）→ 查缺不得的东西（packs.problems）→ 建一只临时控制器把换上来马上要用的量好（warm）。
  全是纯 Python、不碰 Qt 界面。放在单独的子进程里做（PROCESS，multiprocessing spawn；打包版靠 app.py 最先叫的
  freeze_support）：以前在本进程的后台线程里，json.loads（约 19 毫秒，一口气的 C 调用）和备的时候碰上的全量垃圾回收（20～30 毫秒）都拿着 GIL，
  界面每次备有 2 帧超过 25 毫秒、最长 42～87。子进程把量好的模型分块送回来（_child）：先是模型本身（网格、贴图、量好的表都是整块的数组，
  解开约 2 毫秒），再一段一段片段（89 段，每段解开约 0.2 毫秒），最后一个空的；本进程一条专门的线程（_receiver）一块一块收、一块一块解，
  中间放锁，收的时候不让垃圾回收插进来（hold_gc），收完冻结（gc.freeze：大块的模型数据以后不再被全量回收一遍遍扫）。
  起子进程、导入约 0.2 秒，整件约 0.55 秒（本进程里约 0.35 秒）。做完回主线程建 Tuning 和 SoundBank（预载声音 6～10 毫秒，这时是闲的）。
  毛色贴图不在这里解：那只同桌用哪套到换的时候才知道（look.reload）。
- 什么时候备（窗口叫 want）：卡片显示出来 0.4 秒后（名单里用到的、还没备的，离现在这只近的先）、滑动条要去的那只（PetStrip.go）、
  添加页选了哪个模型（_pick_add）。都没赶上：换同桌、添一只不在主线程上等（when_ready 备好了回调，window._pending_pet），
  狗淡出等着、界面照常走；只有删掉现在这只时找旁边那只（window._loadable_neighbour）还用 get 等（那时卡片早开了，早就备好）。
  备好的留着（换回来是热的，多一个模型约 +18～26 MB）；读不出来的这次运行不再试。"""
from __future__ import annotations

import gc
import logging
import multiprocessing
import pickle
import sys
import threading
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from widget import look, packs
from widget.clips import POSTURE_PLANS, SLEEP_PLANS
from widget.gltf import Model
from widget.packs import Pack
from widget.tuning import Tuning
from widget.voice import SoundBank

log = logging.getLogger("kits")

SWITCH_S = 0.0005          # 在本进程里备（PROCESS 关着）时 Python 的线程切换间隔（秒，平时 0.005）：主线程每帧早点拿回 GIL
PROCESS = True             # 在单独的子进程里备；单测大多换回本进程的线程（tests/panel_base.py：快，给 packs.load_model 打的补丁才管用）
CHILD_WAIT_S = 30.0        # 子进程最多等这么久（读坏了、卡住了）：过了就当读不出来
NOSE_CLIPS = ("Pick_up", "Put_down", "Eat_loop", "Drink_loop")   # 鼻子最低那一刻要量的片段（叼球、放球、吃喝：props.spot）


@dataclass
class Kit:
    """一个模型换上去要的东西。tuning、bank 每个包一份，留着（调过的数、预载的声音换回来照旧）。"""
    pack: Pack
    model: Model
    tuning: Tuning
    bank: SoundBank


def warm(model: Model) -> None:
    """换上来马上要用的、按模型量一次的东西先量好（记在模型上，gltf.Model.measured）：各姿势的进入、循环、退出片段的最高点（rest_top、窗口要多高），
    拎起来的姿势，趴着的身长（狗屋门口留多远），跳法的数，叼球放球吃喝时鼻子最低那一刻，渲染器的顶点表和描边表。纯 Python，后台线程里跑。"""
    from widget import render, roam
    from widget.dogctl import DogController
    dog = DogController(model)                    # 临时的一只，量完就丢；量的表在模型上
    for plan in (*POSTURE_PLANS.values(), *SLEEP_PLANS.values()):
        for clip in (*plan.enter, *plan.loop, *plan.exit):
            dog.clip_top(clip)
    dog.posture_tops()                            # 窗口按最高的姿势留多高（换姿势不改窗口）
    dog.lift.prepare()
    dog.lie_span()
    dog.tail_worst()
    roam.leap_measures(dog)
    for clip in NOSE_CLIPS:
        if dict.__contains__(model.clips, clip):
            dog.props.spot(clip)
    render.bound_vertices(model)
    render.outline_weights(model)


def _prepare(pack: Pack) -> Model:
    """后台线程里跑：读模型、查缺不得的东西、量好。读不出来、缺东西抛错（_run 接住）。"""
    before = sys.getswitchinterval()
    sys.setswitchinterval(SWITCH_S)
    try:
        model = packs.load_model(pack)
        missing = packs.problems(model)
        if missing:
            raise ValueError(f"missing {missing}")
        warm(model)
        return model
    finally:
        sys.setswitchinterval(before)


# ---- 子进程备料（PROCESS） ----
_holds = 0
_holds_lock = threading.Lock()


def hold_gc() -> None:
    """先别让自动垃圾回收跑（收模型、换模型那一阵：全量回收一次 20～30 毫秒，拿着 GIL，界面那一帧跟着晚）。和 release_gc 成对，可以叠。"""
    global _holds
    with _holds_lock:
        _holds += 1
        gc.disable()


def release_gc() -> None:
    global _holds
    with _holds_lock:
        _holds = max(0, _holds - 1)
        if _holds == 0:
            gc.enable()


def freeze_heap(collect: bool = False) -> None:
    """现在活着的对象都冻起来（gc.freeze）：以后的全量回收不再扫它们（启动完、每个模型收完叫；模型数据是大头）。collect：先收一遍再冻（启动完）。"""
    if collect:
        gc.collect()
    gc.freeze()


def _child(pack: Pack, conn) -> None:
    """子进程里跑（spawn 起的新 Python，不建界面）：读模型、查、量好（_prepare），分块送回去——先是模型本身（片段表空着），再一段一段片段
    （(名字, 片段)），最后一个空的。读不出来送一条 ("error", 出错的经过)。"""
    try:
        model = _prepare(pack)
        clips = list(dict.items(model.clips))
        model.clips = packs.ClipTable()
        conn.send_bytes(pickle.dumps(model, pickle.HIGHEST_PROTOCOL))
        for item in clips:
            conn.send_bytes(pickle.dumps(item, pickle.HIGHEST_PROTOCOL))
        conn.send_bytes(b"")
    except BaseException:                         # noqa: BLE001 —— 什么错都送回去记日志，子进程自己不弹、不留
        try:
            conn.send_bytes(pickle.dumps(("error", traceback.format_exc()), pickle.HIGHEST_PROTOCOL))
        except Exception:                         # noqa: BLE001 —— 管道断了：那边按读不出来算
            pass
    finally:
        conn.close()


def _prepare_apart(pack: Pack) -> Model:
    """在子进程里备（_child），这边一块一块收、一块一块解（每块拿锁约 0.2 毫秒，中间放锁）；收的时候先别让垃圾回收插进来。读不出来抛错。"""
    ctx = multiprocessing.get_context("spawn")
    recv, send = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child, args=(pack, send), name=f"prepare-{pack.id}", daemon=True)
    proc.start()
    send.close()
    hold_gc()
    try:
        if not recv.poll(CHILD_WAIT_S):
            raise TimeoutError(f"preparing {pack.id} took more than {CHILD_WAIT_S:.0f} s")
        model = pickle.loads(recv.recv_bytes())
        if isinstance(model, tuple):
            raise RuntimeError(f"child failed:\n{model[1]}")
        while True:
            if not recv.poll(CHILD_WAIT_S):
                raise TimeoutError(f"preparing {pack.id} stalled")
            blob = recv.recv_bytes()
            if not blob:
                break
            name, clip = pickle.loads(blob)
            dict.__setitem__(model.clips, name, clip)
        return model
    finally:
        release_gc()
        recv.close()
        proc.join(5.0)
        if proc.is_alive():
            proc.kill()


_pool: Optional[ThreadPoolExecutor] = None


def _receiver() -> ThreadPoolExecutor:
    """备模型的那条线程（用到才开）：等子进程、收、解，一次一件。不和出贴图共用 look.worker（等子进程的那半秒不挡着换毛色）。"""
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kits")
    return _pool


class Kits(QObject):
    """每个模型一份 Kit。store：调参存在哪（窗口的 QSettings，单测里是假的）。"""
    _landed = Signal(str, object)                 # 后台那件做完了：(包, 模型或 None)，回到主线程

    def __init__(self, store, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.store = store
        self._kits: dict[str, Kit] = {}
        self._tunings: dict[str, Tuning] = {}     # 每个包的调参只有一份（tuning）：备好的 Kit、开发者设置页、物件用的都是它
        self._packs: dict[str, Pack] = {}         # 正在备的是哪个包（建 Kit 时要）
        self._jobs: dict[str, Future] = {}
        self._failed: set[str] = set()            # 读不出来的：这次运行不再试
        self._waiting: dict[str, list[Callable[[Optional[Kit]], None]]] = {}   # 备好了要叫的（when_ready）
        self._landed.connect(self._land)

    def adopt(self, pack: Pack, model: Model, tuning: Tuning, bank: SoundBank) -> Kit:
        """启动时那只（窗口自己读的模型、建的调参和声音）。"""
        kit = self._kits[pack.id] = Kit(pack, model, tuning, bank)
        self.share(tuning)
        return kit

    def share(self, tuning: Tuning) -> None:
        """别处已经建好的调参（窗口启动时那只、小球）记成这个包的那一份。"""
        self._tunings[tuning.pack.id] = tuning

    def tuning(self, pack: Pack) -> Tuning:
        """这个包的调参：每个包只有一份——开发者设置页上改的、后台备好的、换过去用的、物件落地读的是同一个对象，
        改了马上生效，换到别的狗就是调过的数（以前后台备好时另建一份，页上改的是另一份，换过去不生效）。"""
        t = self._tunings.get(pack.id)
        if t is None:
            t = self._tunings[pack.id] = Tuning(pack, self.store)
        return t

    def ready(self, pack_id: str) -> bool:
        return pack_id in self._kits

    def ready_kit(self, pack_id: str) -> Optional[Kit]:
        """已经备好的那份（不等、不开始备）；没有 None。"""
        return self._kits.get(pack_id)

    def failed(self, pack_id: str) -> bool:
        return pack_id in self._failed

    def want(self, pack: Pack) -> None:
        """这个模型要用了：还没备、没在备、没读坏过就开始备（后台一次一件，排在出贴图的后面）。"""
        if pack.id in self._kits or pack.id in self._failed:
            return
        self._packs[pack.id] = pack               # 正在备的（丢过又要了）也认回来
        if pack.id in self._jobs:
            return

        apart = PROCESS

        def run() -> Optional[Model]:
            model = None
            try:
                model = _prepare_apart(pack) if apart else _prepare(pack)
            except Exception:                     # noqa: BLE001 —— 文件坏了、缺骨头、建控制器出错、子进程起不来：这个模型这次换不过去，记日志
                log.exception("pack %s can't be prepared", pack.id)
            try:
                self._landed.emit(pack.id, model)
            except RuntimeError:                  # 窗口已经关了
                pass
            return model

        self._jobs[pack.id] = (_receiver() if apart else look.worker()).submit(run)

    def when_ready(self, pack: Pack, then: Callable[[Optional[Kit]], None]) -> None:
        """备好了叫 then(kit)（读不出来 then(None)），在主线程上；已经备好、已经读坏了就当场叫。还没在备就开始备。不等、不挡主线程。"""
        kit = self._kits.get(pack.id)
        if kit is not None or pack.id in self._failed:
            then(kit)
            return
        self._waiting.setdefault(pack.id, []).append(then)
        self.want(pack)

    def get(self, pack: Pack) -> Optional[Kit]:
        """这个模型备好的东西：备好了直接给；正在备就在这里等它做完（卡片顿一下，狗这时本来就看不见）；还没开始就现在开始再等。读不出来 None。"""
        kit = self._kits.get(pack.id)
        if kit is not None or pack.id in self._failed:
            return kit
        self.want(pack)
        job = self._jobs.get(pack.id)
        return self._land(pack.id, job.result()) if job is not None else None

    def _land(self, pack_id: str, model: Optional[Model]) -> Optional[Kit]:
        """后台那件的结果回到主线程（信号到了，或者 get 等到了；先到的那个作数）：建调参、声音，记成备好了。"""
        kit = self._kits.get(pack_id)
        pack = self._packs.pop(pack_id, None)
        self._jobs.pop(pack_id, None)
        if kit is not None or pack is None:
            return kit
        if model is None:
            self._failed.add(pack_id)
            self._call_back(pack_id, None)
            return None
        tuning = self.tuning(pack)
        kit = self._kits[pack_id] = Kit(pack, model, tuning, SoundBank(pack, tuning))
        log.info("pack %s ready: %d clips, %d joints", pack_id, len(model.clips), len(model.skin_joints))
        if PROCESS:
            freeze_heap()                         # 新模型的数据冻起来：以后的全量回收不再扫它
        self._call_back(pack_id, kit)
        return kit

    def _call_back(self, pack_id: str, kit: Optional[Kit]) -> None:
        for then in self._waiting.pop(pack_id, []):
            try:
                then(kit)
            except Exception:                     # noqa: BLE001 —— 一个回调出错不挡别的
                log.exception("when_ready callback for %s failed", pack_id)

    def keep(self, pack_ids) -> None:
        """只留这几个模型的（名单里还有同桌用的、现在这只的），别的丢掉（forget）。"""
        for pack_id in [k for k in (*self._kits, *self._jobs) if k not in pack_ids]:
            self.forget(pack_id)

    def forget(self, pack_id: str) -> None:
        """名单里没有哪只再用这个模型了：丢掉（连出贴图那条线程给它留的遮罩）。正在备的让它备完再丢。"""
        kit = self._kits.pop(pack_id, None)
        if kit is not None:
            look.forget_model(kit.model)
            measured = getattr(kit.model, "measured", None)
            if measured is not None:
                measured.clear()                  # 量好的表里有回指模型的（拎起来的姿势）：拆开这个圈，冻起来的模型靠引用计数也能放掉
        self._failed.discard(pack_id)
        self._waiting.pop(pack_id, None)
        if pack_id in self._jobs:
            self._packs.pop(pack_id, None)        # 做完回来没有包可认：结果不要了
