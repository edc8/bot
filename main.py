from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from typing import Dict, List, Optional
import json
import os
import time
import uuid
from datetime import datetime


@register(
    "aa分账系统",  # 插件唯一标识（改为中文）
    "anchor",     # 插件作者
    "简易AA分账系统（支持创建账单、查看账单、对账明细、标记清账）",  # 插件描述（中文）
    "1.0.0"       # 版本号
)
class AASettlementPlugin(Star):
    def __init__(self, context: Context):
        """插件初始化：加载数据结构与持久化路径"""
        super().__init__(context)
        # 核心数据结构（按用户ID隔离账单）
        self.aa_bills: Dict[str, List[Dict]] = {}  # {用户ID: [账单列表]}
        self.settlement_records: Dict[str, List[Dict]] = {}  # {用户ID: [清账记录]}
        # 数据持久化路径（插件所在目录）
        self.bills_path = os.path.join(os.path.dirname(__file__), "aa账单数据.json")  # 文件名改为中文
        self.records_path = os.path.join(os.path.dirname(__file__), "aa清账记录.json")  # 文件名改为中文
        # 加载历史数据
        self._加载历史数据()

    async def initialize(self):
        """异步初始化方法（框架自动调用）"""
        logger.info("AA分账系统插件初始化完成，已加载历史账单数据")

    # ---------------------- 指令1：创建账单（中文指令：/创建账单） ----------------------
    @filter.command("创建账单")  # 指令名改为中文
    async def 创建账单(self, event: AstrMessageEvent):  # 方法名改为中文
        """
        创建AA账单（中文指令说明）
        用法：/创建账单 [参与人1] [参与人2] ... [金额] [描述可选]
        示例1：/创建账单 陈 100（1人参与，默认描述“日常消费”）
        示例2：/创建账单 张三 李四 600 聚餐（2人参与，描述“聚餐”）
        """
        # 获取用户输入的纯文本消息
        消息内容 = event.message_str.strip()  # 变量名改为中文
        # 解析指令参数（去除 "/创建账单" 前缀）
        参数列表 = list(filter(None, 消息内容.split(" ")))[1:]  # 前1个元素是 "/创建账单"

        # 基础参数校验
        if len(参数列表) < 2:
            yield event.plain_result(
                "❌ 指令格式错误！正确用法：\n"
                "📌 简单模式：/创建账单 [参与人] [金额]（示例：/创建账单 陈 100）\n"
                "📌 完整模式：/创建账单 [参与人1] [参与人2] ... [金额] [描述]（示例：/创建账单 张三 李四 600 聚餐）"
            )
            return

        # 解析金额（从后往前找第一个数字）
        总金额 = None
        金额索引 = -1
        for 索引 in reversed(range(len(参数列表))):
            try:
                总金额 = float(参数列表[索引])
                金额索引 = 索引
                break
            except ValueError:
                continue

        # 金额合法性校验
        if 总金额 is None or 总金额 <= 0:
            yield event.plain_result("❌ 金额错误！请输入有效的正数（支持小数，如25.5）")
            return

        # 提取参与人、描述、付款人信息
        参与人列表 = 参数列表[:金额索引]
        消费描述 = " ".join(参数列表[金额索引+1:]) if (金额索引 + 1 < len(参数列表)) else "日常消费"
        付款人ID = event.get_sender_id()
        付款人名称 = event.get_sender_name() or f"用户{付款人ID[:4]}"  # 无用户名时用ID前4位

        # 补充付款人到参与人列表并去重
        if 付款人名称 not in 参与人列表:
            参与人列表.append(付款人名称)
        参与人列表 = list(set(参与人列表))  # 去重
        参与人数 = len(参与人列表)

        # 计算分摊金额与分账误差（误差由付款人承担）
        每人分摊 = round(总金额 / 参与人数, 2)
        分账误差 = round(总金额 - (每人分摊 * 参与人数), 2)

        # 生成账单基础信息
        账单ID = str(uuid.uuid4())[:6]  # 6位UUID作为账单ID
        创建时间 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        时间戳 = int(time.time())

        # 构建账单详情
        账单信息 = {
            "账单ID": 账单ID,  # 键名改为中文
            "付款人": {"ID": 付款人ID, "名称": 付款人名称},  # 键名改为中文
            "总金额": round(总金额, 2),
            "消费描述": 消费描述,
            "参与人": 参与人列表,
            "参与人数": 参与人数,
            "每人分摊": 每人分摊,
            "分账误差": 分账误差,
            "状态": "待清账",  # 状态改为中文（待清账/已清账）
            "创建时间": 创建时间,
            "时间戳": 时间戳,
            "清账时间": None,
            "清账人": None,
            "债务关系": self._生成债务关系(付款人名称, 参与人列表, 每人分摊)  # 键名改为中文
        }

        # 保存账单到当前用户的账单列表
        self.aa_bills.setdefault(付款人ID, []).append(账单信息)
        self._保存数据()  # 持久化数据

        # 生成回复结果
        回复内容 = (
            "✅ AA账单创建成功！\n"
            "=" * 40 + "\n"
            f"🆔 账单ID：{账单ID}（用于对账/清账）\n"
            f"💸 付款人：{付款人名称}\n"
            f"📝 消费描述：{消费描述}\n"
            f"💰 总金额：{账单信息['总金额']}元\n"
            f"👥 参与人（{参与人数}人）：{', '.join(参与人列表)}\n"
            f"🧮 每人分摊：{每人分摊}元\n"
        )
        if 分账误差 > 0:
            回复内容 += f"⚠️  分账误差：{付款人名称}多承担{分账误差}元\n"
        回复内容 += (
            f"⏰ 创建时间：{创建时间}\n"
            "=" * 40 + "\n"
            "💡 后续操作：\n"
            "  查看所有账单：/查看账单\n"
            f"  查看债务明细：/对账明细 {账单ID}\n"
            f"  标记清账：/标记清账 {账单ID}"
        )
        yield event.plain_result(回复内容)

    # ---------------------- 指令2：查看账单（中文指令：/查看账单） ----------------------
    @filter.command("查看账单")  # 指令名改为中文
    async def 查看账单(self, event: AstrMessageEvent):  # 方法名改为中文
        """
        查看当前用户的所有AA账单（中文指令说明）
        用法：/查看账单
        功能：按创建时间倒序显示，区分待清账/已清账状态
        """
        用户ID = event.get_sender_id()
        用户账单列表 = self.aa_bills.get(用户ID, [])  # 获取当前用户的账单

        # 无账单时的回复
        if not 用户账单列表:
            yield event.plain_result(
                "📋 暂无AA账单\n"
                "💡 快速创建：/创建账单 [参与人] [金额]（示例：/创建账单 陈 100）"
            )
            return

        # 按创建时间倒序排序（最新在前），最多显示10条
        排序后的账单 = sorted(用户账单列表, key=lambda x: x["时间戳"], reverse=True)[:10]
        # 统计待清账/已清账数量
        待清账数量 = len([b for b in 用户账单列表 if b["状态"] == "待清账"])
        已清账数量 = len(用户账单列表) - 待清账数量

        # 构建账单列表回复
        回复内容 = (
            f"📊 我的AA账单列表（共{len(用户账单列表)}条，显示最近10条）\n"
            f"   🔴 待清账：{待清账数量}条 | 🟢 已清账：{已清账数量}条\n"
            "-" * 50 + "\n"
        )
        for 序号, 账单 in enumerate(排序后的账单, 1):
            状态标签 = "🔴 待清账" if 账单["状态"] == "待清账" else "🟢 已清账"
            操作提示 = f"操作：/标记清账 {账单['账单ID']}" if 账单["状态"] == "待清账" else f"清账时间：{账单['清账时间']}"
            
            回复内容 += (
                f"{序号}. 账单ID：{账单['账单ID']} | {状态标签}\n"
                f"   描述：{账单['消费描述']}\n"
                f"   付款人：{账单['付款人']['名称']} | 金额：{账单['总金额']}元\n"
                f"   参与人：{', '.join(账单['参与人'])}\n"
                f"   时间：{账单['创建时间']}\n"
                f"   {操作提示}\n"
                "-" * 50 + "\n"
            )
        yield event.plain_result(回复内容)

    # ---------------------- 指令3：对账明细（中文指令：/对账明细） ----------------------
    @filter.command("对账明细")  # 指令名改为中文
    async def 对账明细(self, event: AstrMessageEvent):  # 方法名改为中文
        """
        查看指定账单的债务明细（中文指令说明）
        用法：/对账明细 [账单ID]
        示例：/对账明细 abc123
        """
        消息内容 = event.message_str.strip()
        参数列表 = list(filter(None, 消息内容.split(" ")))[1:]  # 提取 "/对账明细" 后的参数

        # 缺少账单ID的处理
        if not 参数列表:
            yield event.plain_result(
                "❌ 缺少账单ID！\n"
                "正确用法：/对账明细 [账单ID]\n"
                "示例：/对账明细 abc123\n"
                "提示：通过 /查看账单 可查看所有账单ID"
            )
            return

        目标账单ID = 参数列表[0]
        用户ID = event.get_sender_id()
        目标账单 = None

        # 查找指定ID的账单
        for 账单 in self.aa_bills.get(用户ID, []):
            if 账单["账单ID"] == 目标账单ID:
                目标账单 = 账单
                break

        # 账单不存在的处理
        if not 目标账单:
            yield event.plain_result(
                f"❌ 未找到ID为「{目标账单ID}」的账单\n"
                "💡 可能原因：\n"
                "   1. 账单ID输入错误（区分大小写）\n"
                "   2. 该账单不属于当前用户\n"
                "提示：通过 /查看账单 查看所有账单"
            )
            return

        # 构建债务明细回复
        状态标签 = "🔴 待清账" if 目标账单["状态"] == "待清账" else "🟢 已清账"
        回复内容 = (
            f"📊 账单「{目标账单ID}」债务明细 | {状态标签}\n"
            "=" * 40 + "\n"
            f"📝 描述：{目标账单['消费描述']}\n"
            f"💸 付款人：{目标账单['付款人']['名称']}（垫付{目标账单['总金额']}元）\n"
            f"🧮 每人分摊：{目标账单['每人分摊']}元\n"
            "\n【债务关系】\n"
        )

        # 遍历债务列表
        债务列表 = 目标账单["债务关系"]
        if not 债务列表:
            回复内容 += "⚠️  无债务关系（仅付款人一人参与）\n"
        else:
            for 债务 in 债务列表:
                回复内容 += f"👉 {债务['债务人']} 应支付 {债务['债权人']} {债务['金额']}元\n"

        # 分账误差说明
        if 目标账单["分账误差"] > 0:
            回复内容 += (
                f"\n⚠️  误差说明：\n"
                f"{目标账单['付款人']['名称']}多承担{目标账单['分账误差']}元（总金额无法均分）\n"
            )

        # 状态提示
        if 目标账单["状态"] == "待清账":
            回复内容 += f"\n💡 提示：所有债务结清后，执行 /标记清账 {目标账单ID} 标记清账\n"
        else:
            回复内容 += f"\n✅ 已清账：{目标账单['清账时间']}（{目标账单['清账人']['名称']}操作）\n"

        yield event.plain_result(回复内容)

    # ---------------------- 指令4：标记清账（中文指令：/标记清账） ----------------------
    @filter.command("标记清账")  # 指令名改为中文
    async def 标记清账(self, event: AstrMessageEvent):  # 方法名改为中文
        """
        将指定账单标记为已清账（中文指令说明）
        用法：/标记清账 [账单ID]
        示例：/标记清账 abc123
        """
        消息内容 = event.message_str.strip()
        参数列表 = list(filter(None, 消息内容.split(" ")))[1:]  # 提取 "/标记清账" 后的参数

        # 缺少账单ID的处理
        if not 参数列表:
            yield event.plain_result(
                "❌ 缺少账单ID！\n"
                "正确用法：/标记清账 [账单ID]\n"
                "示例：/标记清账 abc123\n"
                "提示：通过 /查看账单 可查看所有账单ID"
            )
            return

        目标账单ID = 参数列表[0]
        用户ID = event.get_sender_id()
        清账人名称 = event.get_sender_name() or f"用户{用户ID[:4]}"
        清账时间 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        目标账单 = None

        # 查找指定ID的账单
        for 账单 in self.aa_bills.get(用户ID, []):
            if 账单["账单ID"] == 目标账单ID:
                目标账单 = 账单
                break

        # 账单不存在的处理
        if not 目标账单:
            yield event.plain_result(
                f"❌ 未找到ID为「{目标账单ID}」的账单\n"
                "提示：通过 /查看账单 查看所有账单"
            )
            return

        # 已清账的处理
        if 目标账单["状态"] == "已清账":
            yield event.plain_result(
                f"✅ 账单「{目标账单ID}」已是已清账状态\n"
                "=" * 30 + "\n"
                f"清账时间：{目标账单['清账时间']}\n"
                f"清账人：{目标账单['清账人']['名称']}\n"
                "=" * 30
            )
            return

        # 更新账单状态为已清账
        目标账单["状态"] = "已清账"
        目标账单["清账时间"] = 清账时间
        目标账单["清账人"] = {"ID": 用户ID, "名称": 清账人名称}

        # 记录清账记录
        self.settlement_records.setdefault(用户ID, []).append({
            "记录ID": str(uuid.uuid4())[:8],
            "账单ID": 目标账单ID,
            "消费描述": 目标账单["消费描述"],
            "总金额": 目标账单["总金额"],
            "清账人": 清账人名称,
            "清账时间": 清账时间,
            "时间戳": int(time.time())
        })

        # 保存数据
        self._保存数据()

        # 生成清账成功回复
        回复内容 = (
            f"✅ 账单「{目标账单ID}」已标记为已清账！\n"
            "=" * 40 + "\n"
            f"📝 描述：{目标账单['消费描述']}\n"
            f"💰 金额：{目标账单['总金额']}元\n"
            f"⏰ 清账时间：{清账时间}\n"
            f"🧑 清账人：{清账人名称}\n"
            "=" * 40
        )
        yield event.plain_result(回复内容)

    # ---------------------- 指令5：帮助中心（中文指令：/帮助中心） ----------------------
    @filter.command("帮助中心")  # 指令名改为中文
    async def 帮助中心(self, event: AstrMessageEvent):  # 方法名改为中文
        """
        查看AA分账系统的所有指令帮助（中文指令说明）
        用法：/帮助中心
        """
        帮助文本 = (
            "📊 AA分账系统帮助中心（v1.0.0）\n"
            "=" * 45 + "\n"
            "【所有可用指令】\n"
            "\n"
            "1. 创建AA账单\n"
            "   📌 指令：/创建账单 [参与人1] [参与人2] ... [金额] [描述可选]\n"
            "   📌 示例：/创建账单 陈 100（简单模式）\n"
            "   📌 示例：/创建账单 张三 李四 600 聚餐（完整模式）\n"
            "   📌 功能：创建账单，自动计算每人分摊金额\n"
            "\n"
            "2. 查看所有账单\n"
            "   📌 指令：/查看账单\n"
            "   📌 功能：按时间倒序显示所有账单，区分待清账/已清账\n"
            "\n"
            "3. 查看债务明细\n"
            "   📌 指令：/对账明细 [账单ID]\n"
            "   📌 示例：/对账明细 abc123\n"
            "   📌 功能：显示指定账单的债务关系（谁该给谁钱）\n"
            "\n"
            "4. 标记账单清账\n"
            "   📌 指令：/标记清账 [账单ID]\n"
            "   📌 示例：/标记清账 abc123\n"
            "   📌 功能：将账单标记为已清账，记录清账人/时间\n"
            "\n"
            "5. 查看帮助\n"
            "   📌 指令：/帮助中心\n"
            "   📌 功能：显示本帮助中心\n"
            "=" * 45 + "\n"
            "📢 提示：账单数据按用户隔离，仅自己可见"
        )
        yield event.plain_result(帮助文本)

    # ---------------------- 辅助方法（全部改为中文） ----------------------
    def _生成债务关系(self, 付款人: str, 参与人列表: List[str], 金额: float) -> List[Dict]:
        """生成债务关系列表：参与人向付款人支付分摊金额"""
        return [
            {"债务人": 人员, "债权人": 付款人, "金额": 金额}  # 键名改为中文
            for 人员 in 参与人列表 if 人员 != 付款人
        ]

    def _加载历史数据(self):
        """加载历史数据（从JSON文件读取）"""
        # 加载账单数据
        try:
            if os.path.exists(self.bills_path):
                with open(self.bills_path, "r", encoding="utf-8") as f:
                    self.aa_bills = json.load(f)
                logger.info(f"AA分账系统：成功加载{len(self.aa_bills)}个用户的账单数据")
            else:
                logger.info("AA分账系统：账单数据文件不存在，初始化空数据")
        except Exception as e:
            logger.error(f"AA分账系统：加载账单数据失败：{str(e)}，初始化空数据")
            self.aa_bills = {}

        # 加载清账记录
        try:
            if os.path.exists(self.records_path):
                with open(self.records_path, "r", encoding="utf-8") as f:
                    self.settlement_records = json.load(f)
                logger.info(f"AA分账系统：成功加载{len(self.settlement_records)}个用户的清账记录")
            else:
                logger.info("AA分账系统：清账记录文件不存在，初始化空数据")
        except Exception as e:
            logger.error(f"AA分账系统：加载清账记录失败：{str(e)}，初始化空数据")
            self.settlement_records = {}

    def _保存数据(self):
        """保存数据到JSON文件（持久化）"""
        # 保存账单数据
        try:
            with open(self.bills_path, "w", encoding="utf-8") as f:
                json.dump(self.aa_bills, f, ensure_ascii=False, indent=2)
            logger.info("AA分账系统：账单数据保存成功")
        except Exception as e:
            logger.error(f"AA分账系统：保存账单数据失败：{str(e)}")

        # 保存清账记录
        try:
            with open(self.records_path, "w", encoding="utf-8") as f:
                json.dump(self.settlement_records, f, ensure_ascii=False, indent=2)
            logger.info("AA分账系统：清账记录保存成功")
        except Exception as e:
            logger.error(f"AA分账系统：保存清账记录失败：{str(e)}")

    async def terminate(self):
        """插件卸载/停用时调用，确保数据保存"""
        self._保存数据()
        logger.info("AA分账系统插件已卸载，所有数据已持久化保存")
