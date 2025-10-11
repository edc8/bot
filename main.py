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
    "aa_settlement",  # 插件唯一标识
    "YourName",       # 插件作者
    "简洁AA分账系统（支持/aa 陈 100等简洁指令）",  # 插件描述
    "1.0.0"           # 版本号
)
class AASettlementPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 核心数据结构（用户ID隔离账单）
        self.aa_bills: Dict[str, List[Dict]] = {}  # {用户ID: [账单列表]}
        self.settlement_records: Dict[str, List[Dict]] = {}  # {用户ID: [清账记录]}
        # 数据持久化路径
        self.bills_path = os.path.join(os.path.dirname(__file__), "aa_bills.json")
        self.records_path = os.path.join(os.path.dirname(__file__), "settlement_records.json")
        # 加载历史数据
        self._load_persistent_data()

    async def initialize(self):
        """异步初始化（框架自动调用）"""
        logger.info("简洁AA分账系统初始化完成，已加载历史数据")

    # ---------------------- 核心：单一指令入口 /aa，自动判断功能 ----------------------
    @filter.command("aa")
    async def aa_main_handler(self, event: AstrMessageEvent):
        """
        单一指令入口，自动识别功能：
        - 创建账单：/aa [参与人] [金额] [描述可选]（例：/aa 陈 100 | /aa 张三 李四 600 聚餐）
        - 查看所有账单：/aa 查（例：/aa 查）
        - 查看债务明细：/aa 对账 [账单ID]（例：/aa 对账 abc123）
        - 标记清账：/aa 清账 [账单ID]（例：/aa 清账 abc123）
        - 查看帮助：/aa 或 /aa 帮助（例：/aa 帮助）
        """
        # 参考示例：获取用户纯文本消息并解析参数
        message_str = event.message_str.strip()
        # 分割参数（去除 "/aa" 前缀，得到后续所有参数）
        params = list(filter(None, message_str.split(" ")))[1:]  # params 为 "/aa" 后的所有内容

        # 1. 无参数 / 仅输入 "帮助" → 显示帮助
        if not params or params[0] == "帮助":
            yield event.plain_result(self._get_help_text())
        
        # 2. 参数为 "查" → 查看所有账单
        elif params[0] == "查":
            yield event.plain_result(await self._list_all_bills(event))
        
        # 3. 参数为 "对账" → 查看债务明细（需账单ID）
        elif params[0] == "对账":
            if len(params) < 2:  # 缺少账单ID
                yield event.plain_result("❌ 格式错误！正确用法：/aa 对账 [账单ID]（例：/aa 对账 abc123）")
            else:
                yield event.plain_result(await self._show_debt_detail(event, params[1]))
        
        # 4. 参数为 "清账" → 标记账单清账（需账单ID）
        elif params[0] == "清账":
            if len(params) < 2:  # 缺少账单ID
                yield event.plain_result("❌ 格式错误！正确用法：/aa 清账 [账单ID]（例：/aa 清账 abc123）")
            else:
                yield event.plain_result(await self._mark_bill_cleared(event, params[1]))
        
        # 5. 其他参数组合 → 默认为创建账单（/aa [参与人] [金额] [描述可选]）
        else:
            yield event.plain_result(await self._create_bill(event, params))

    # ---------------------- 功能1：创建账单（核心支持 /aa 陈 100 格式） ----------------------
    async def _create_bill(self, event: AstrMessageEvent, params: List[str]) -> str:
        """创建账单，支持：/aa 陈 100（简单）、/aa 张三 李四 600 聚餐（带描述）"""
        # 基础校验：至少需要 参与人 + 金额 2个参数
        if len(params) < 2:
            return (
                "❌ 创建账单格式错误！\n"
                "📌 简单模式（参与人+金额）：/aa [参与人] [金额]（例：/aa 陈 100）\n"
                "📌 完整模式（含描述）：/aa [参与人1] [参与人2] ... [金额] [描述]（例：/aa 张三 李四 600 聚餐）"
            )

        # 解析金额：从后往前找第一个数字（兼容描述含数字，如 /aa 陈 100 2024午餐）
        total_amount = None
        amount_index = -1
        for idx in reversed(range(len(params))):
            try:
                total_amount = float(params[idx])
                amount_index = idx
                break
            except ValueError:
                continue  # 不是数字则继续向前找

        # 金额合法性校验
        if total_amount is None or total_amount <= 0:
            return "❌ 金额错误！请输入有效的正数（支持小数，如 25.5 表示25.5元）"

        # 提取核心信息
        participants = params[:amount_index]  # 金额前的所有参数 = 参与人列表
        total_amount = round(total_amount, 2)  # 金额保留2位小数
        # 金额后的参数 = 消费描述（无则默认"日常消费"）
        consumption_desc = " ".join(params[amount_index+1:]) if (amount_index + 1 < len(params)) else "日常消费"

        # 获取付款人信息（当前指令发送者）
        payer_id = event.get_sender_id()
        payer_name = event.get_sender_name() or f"用户{payer_id[:4]}"  # 无用户名用ID前4位

        # 补充付款人到参与人列表并去重（避免遗漏自己）
        if payer_name not in participants:
            participants.append(payer_name)
        participants = list(set(participants))  # 去重（如重复输入同一人）
        total_people = len(participants)

        # 计算分摊金额与分账误差（误差由付款人承担，确保总金额正确）
        per_person_amount = round(total_amount / total_people, 2)
        calculated_total = round(per_person_amount * total_people, 2)
        amount_diff = round(total_amount - calculated_total, 2)

        # 生成账单唯一信息
        bill_id = str(uuid.uuid4())[:6]  # 6位短ID（易记，如 abc123）
        create_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        create_timestamp = int(time.time())  # 时间戳（用于排序）

        # 构建账单详情
        bill_detail = {
            "bill_id": bill_id,
            "payer": {"id": payer_id, "name": payer_name},
            "total_amount": total_amount,
            "description": consumption_desc,
            "participants": participants,
            "total_people": total_people,
            "per_person": per_person_amount,
            "diff": amount_diff,
            "status": "pending",  # 状态：pending=待清账，cleared=已清账
            "create_time": create_time,
            "timestamp": create_timestamp,
            "clear_time": None,
            "clearer": None,
            "debts": self._generate_debt_relations(payer_name, participants, per_person_amount)
        }

        # 保存账单（按用户ID隔离）
        self.aa_bills.setdefault(payer_id, []).append(bill_detail)
        self._save_persistent_data()  # 持久化避免重启丢失

        # 生成创建成功回复
        result = (
            "✅ 账单创建成功！\n"
            "=" * 40 + "\n"
            f"🆔 账单ID：{bill_id}\n"
            f"💸 付款人：{payer_name}\n"
            f"📝 描述：{consumption_desc}\n"
            f"💰 总金额：{total_amount}元\n"
            f"👥 参与人（{total_people}人）：{', '.join(participants)}\n"
            f"🧮 每人分摊：{per_person_amount}元\n"
        )
        if amount_diff > 0:
            result += f"⚠️  分账误差：{payer_name}多承担{amount_diff}元\n"
        result += (
            f"⏰ 时间：{create_time}\n"
            "=" * 40 + "\n"
            "💡 后续操作：\n"
            "  查看所有账单：/aa 查\n"
            f"  标记清账：/aa 清账 {bill_id}\n"
            f"  查看债务：/aa 对账 {bill_id}"
        )
        return result

    # ---------------------- 功能2：查看所有账单（/aa 查） ----------------------
    async def _list_all_bills(self, event: AstrMessageEvent) -> str:
        """查看当前用户所有账单，按时间倒序排列"""
        user_id = event.get_sender_id()
        user_bills = self.aa_bills.get(user_id, [])

        # 无账单时提示
        if not user_bills:
            return (
                "📋 暂无AA账单\n"
                "💡 快速创建：\n"
                "   /aa [参与人] [金额]（例：/aa 陈 100）\n"
                "   /aa [参与人] [金额] [描述]（例：/aa 陈 100 午餐）"
            )

        # 排序（最新在前）+ 统计状态
        sorted_bills = sorted(user_bills, key=lambda x: x["timestamp"], reverse=True)[:10]  # 最多显示10条
        pending_count = len([b for b in user_bills if b["status"] == "pending"])
        cleared_count = len(user_bills) - pending_count

        # 构建账单列表
        result = (
            f"📊 我的AA账单（共{len(user_bills)}条，显示最近10条）\n"
            f"   🔴 待清账：{pending_count}条 | 🟢 已清账：{cleared_count}条\n"
            "-" * 50 + "\n"
        )
        for idx, bill in enumerate(sorted_bills, 1):
            status_tag = "🔴 待清账" if bill["status"] == "pending" else "🟢 已清账"
            operation = f"操作：/aa 清账 {bill['bill_id']}" if bill["status"] == "pending" else f"清账时间：{bill['clear_time']}"
            
            result += (
                f"{idx}. 账单ID：{bill['bill_id']} | {status_tag}\n"
                f"   描述：{bill['description']}\n"
                f"   付款人：{bill['payer']['name']} | 金额：{bill['total_amount']}元\n"
                f"   参与人：{', '.join(bill['participants'])}\n"
                f"   创建时间：{bill['create_time']}\n"
                f"   {operation}\n"
                "-" * 50 + "\n"
            )
        return result

    # ---------------------- 功能3：查看债务明细（/aa 对账 [账单ID]） ----------------------
    async def _show_debt_detail(self, event: AstrMessageEvent, bill_id: str) -> str:
        """查看指定账单的债务关系（谁该给谁钱）"""
        user_id = event.get_sender_id()
        # 查找目标账单
        target_bill = None
        for bill in self.aa_bills.get(user_id, []):
            if bill["bill_id"] == bill_id:
                target_bill = bill
                break

        # 账单不存在处理
        if not target_bill:
            return (
                f"❌ 未找到ID为「{bill_id}」的账单\n"
                "💡 可能原因：\n"
                "   1. 账单ID输入错误\n"
                "   2. 该账单不属于当前用户\n"
                "提示：通过 /aa 查 查看所有账单ID"
            )

        # 构建债务明细
        status_tag = "🔴 待清账" if target_bill["status"] == "pending" else "🟢 已清账"
        result = (
            f"📊 账单「{bill_id}」债务明细 | {status_tag}\n"
            "=" * 40 + "\n"
            f"📝 描述：{target_bill['description']}\n"
            f"💸 付款人：{target_bill['payer']['name']}（垫付{target_bill['total_amount']}元）\n"
            f"🧮 每人分摊：{target_bill['per_person']}元\n"
            "\n【债务关系】\n"
        )

        # 遍历债务列表
        debts = target_bill["debts"]
        if not debts:
            result += "⚠️  无债务关系（仅付款人一人参与）\n"
        else:
            for debt in debts:
                result += f"👉 {debt['debtor']} 应支付 {debt['creditor']} {debt['amount']}元\n"

        # 分账误差说明
        if target_bill["diff"] > 0:
            result += (
                f"\n⚠️  误差说明：\n"
                f"总金额（{target_bill['total_amount']}元）无法均分，\n"
                f"{target_bill['payer']['name']}多承担{target_bill['diff']}元\n"
            )

        # 状态提示
        if target_bill["status"] == "pending":
            result += f"\n💡 提示：所有债务结清后，执行 /aa 清账 {bill_id} 标记\n"
        else:
            result += f"\n✅ 已清账：{target_bill['clear_time']}（{target_bill['clearer']['name']}操作）\n"

        return result

    # ---------------------- 功能4：标记账单清账（/aa 清账 [账单ID]） ----------------------
    async def _mark_bill_cleared(self, event: AstrMessageEvent, bill_id: str) -> str:
        """将指定账单标记为已清账"""
        user_id = event.get_sender_id()
        clearer_name = event.get_sender_name() or f"用户{user_id[:4]}"
        clear_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 查找目标账单
        target_bill = None
        for bill in self.aa_bills.get(user_id, []):
            if bill["bill_id"] == bill_id:
                target_bill = bill
                break

        # 账单不存在处理
        if not target_bill:
            return f"❌ 未找到ID为「{bill_id}」的账单\n💡 查看所有账单：/aa 查"

        # 已清账处理
        if target_bill["status"] == "cleared":
            return (
                f"✅ 账单「{bill_id}」已是已清账状态\n"
                "=" * 30 + "\n"
                f"清账时间：{target_bill['clear_time']}\n"
                f"操作人：{target_bill['clearer']['name']}\n"
                "=" * 30
            )

        # 更新账单状态
        target_bill["status"] = "cleared"
        target_bill["clear_time"] = clear_time
        target_bill["clearer"] = {"id": user_id, "name": clearer_name}

        # 记录清账记录
        self.settlement_records.setdefault(user_id, []).append({
            "record_id": str(uuid.uuid4())[:8],
            "bill_id": bill_id,
            "description": target_bill["description"],
            "amount": target_bill["total_amount"],
            "clearer": clearer_name,
            "clear_time": clear_time,
            "timestamp": int(time.time())
        })

        # 保存数据
        self._save_persistent_data()

        # 生成清账成功回复
        result = (
            f"✅ 账单「{bill_id}」已标记为已清账！\n"
            "=" * 40 + "\n"
            f"📝 描述：{target_bill['description']}\n"
            f"💰 总金额：{target_bill['total_amount']}元\n"
            f"⏰ 清账时间：{clear_time}\n"
            f"🧑 操作人：{clearer_name}\n"
            "=" * 40
        )
        return result

    # ---------------------- 辅助方法 ----------------------
    def _generate_debt_relations(self, payer: str, participants: List[str], amount: float) -> List[Dict]:
        """生成债务关系：参与人向付款人支付分摊金额"""
        return [
            {"debtor": person, "creditor": payer, "amount": amount}
            for person in participants if person != payer
        ]

    def _get_help_text(self) -> str:
        """生成帮助文本（适配简洁指令）"""
        return (
            "📊 简洁AA分账系统帮助（v1.0.0）\n"
            "=" * 40 + "\n"
            "【所有可用指令】\n"
            "\n"
            "1. 创建账单（最常用）\n"
            "   📌 格式：/aa [参与人] [金额] [描述可选]\n"
            "   📌 示例1：/aa 陈 100（1人参与，总金额100元）\n"
            "   📌 示例2：/aa 张三 李四 600 聚餐（2人参与，描述「聚餐」）\n"
            "\n"
            "2. 查看所有账单\n"
            "   📌 格式：/aa 查\n"
            "   📌 功能：显示所有账单，区分待清账/已清账\n"
            "\n"
            "3. 查看债务明细\n"
            "   📌 格式：/aa 对账 [账单ID]\n"
            "   📌 示例：/aa 对账 abc123（查看ID为abc123的账单债务）\n"
            "\n"
            "4. 标记账单清账\n"
            "   📌 格式：/aa 清账 [账单ID]\n"
            "   📌 示例：/aa 清账 abc123（标记ID为abc123的账单为已清账）\n"
            "\n"
            "5. 查看帮助\n"
            "   📌 格式：/aa 或 /aa 帮助\n"
            "=" * 40 + "\n"
            "📢 提示：账单数据按用户隔离，仅自己可见"
        )

    def _load_persistent_data(self):
        """加载历史数据（从JSON文件）"""
        # 加载账单
        try:
            if os.path.exists(self.bills_path):
                with open(self.bills_path, "r", encoding="utf-8") as f:
                    self.aa_bills = json.load(f)
                logger.info(f"AA分账系统：加载{len(self.aa_bills)}个用户的账单")
            else:
                logger.info("AA分账系统：账单文件不存在，初始化空数据")
        except Exception as e:
            logger.error(f"加载账单失败：{e}，初始化空数据")
            self.aa_bills = {}

        # 加载清账记录
        try:
            if os.path.exists(self.records_path):
                with open(self.records_path, "r", encoding="utf-8") as f:
                    self.settlement_records = json.load(f)
                logger.info(f"AA分账系统：加载{len(self.settlement_records)}个用户的清账记录")
            else:
                logger.info("AA分账系统：清账记录文件不存在，初始化空数据")
        except Exception as e:
            logger.error(f"加载清账记录失败：{e}，初始化空数据")
            self.settlement_records = {}

    def _save_persistent_data(self):
        """保存数据到JSON文件（持久化）"""
        # 保存账单
        try:
            with open(self.bills_path, "w", encoding="utf-8") as f:
                json.dump(self.aa_bills, f, ensure_ascii=False, indent=2)
            logger.info("AA分账系统：账单数据保存成功")
        except Exception as e:
            logger.error(f"保存账单失败：{e}")

        # 保存清账记录
        try:
            with open(self.records_path, "w", encoding="utf-8") as f:
                json.dump(self.settlement_records, f, ensure_ascii=False, indent=2)
            logger.info("AA分账系统：清账记录保存成功")
        except Exception as e:
            logger.error(f"保存清账记录失败：{e}")

    async def terminate(self):
        """插件卸载时保存数据（框架自动调用）"""
        self._save_persistent_data()
        logger.info("简洁AA分账系统已卸载，所有数据已保存")
