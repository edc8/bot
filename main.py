# 从filter模块中正确导入filter装饰器（关键修复）
from astrbot.api.event.filter import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from typing import Dict, List, Optional
import json
import os
import time
import uuid
from datetime import datetime


@register(
    "aa_settlement",  # 插件唯一标识（不可重复）
    "anchor",          # 插件作者
    "简易AA记账机器人（支持创建账单、查询、对账、清账）",  # 插件描述
    "2.3.0",           # 插件版本（已更新版本号）
    "https://github.com/edc8/bot"  # 插件仓库地址（与安装地址一致）
)
class AASettlementPlugin(Star):
    def __init__(self, context: Context):
        """插件初始化：加载数据与初始化结构"""
        super().__init__(context)
        # 核心数据结构（按用户ID隔离数据）
        self.aa_bills: Dict[str, List[Dict]] = {}  # 存储账单：key=用户ID，value=账单列表
        self.settlement_records: Dict[str, List[Dict]] = {}  # 存储清账记录
        
        # 数据持久化路径（插件目录下）
        self.bills_path = os.path.join(os.path.dirname(__file__), "aa_bills.json")
        self.records_path = os.path.join(os.path.dirname(__file__), "settlement_records.json")
        
        # 加载历史数据
        self._load_persistent_data()

    # ---------------------- 消息处理入口 ----------------------
    @filter()
    async def handle_message(self, event: AstrMessageEvent):
        """处理所有消息，只响应/aa开头的指令"""
        content = event.get_content().strip()
        if not content.startswith("/aa"):
            return  # 忽略非/aa指令
        
        # 解析指令参数（处理多空格情况）
        parts = list(filter(None, content.split(" ")))[1:]  # 去除"/aa"后的参数列表
        response = await self._process_command(event, parts)
        
        # 回复结果
        if response:
            await event.reply(response)

    # ---------------------- 指令处理逻辑 ----------------------
    async def _process_command(self, event: AstrMessageEvent, params: List[str]) -> str:
        """分发不同指令到对应处理函数"""
        if not params:
            return self._get_help_text()  # /aa 显示帮助
        
        cmd = params[0]
        args = params[1:] if len(params) > 1 else []
        
        # 创建账单：/aa 参与人 金额 [描述]
        if cmd not in ["查", "对账", "清账", "帮助"]:
            return await self._create_bill(event, [cmd] + args)
        
        # 查看账单列表：/aa 查
        elif cmd == "查":
            return await self._list_bills(event)
        
        # 查看债务明细：/aa 对账 账单ID
        elif cmd == "对账":
            if not args:
                return "❌ 请指定账单ID！\n用法：/aa 对账 [账单ID]\n示例：/aa 对账 abc123"
            return await self._show_debt(event, args[0])
        
        # 标记清账：/aa 清账 账单ID
        elif cmd == "清账":
            if not args:
                return "❌ 请指定账单ID！\n用法：/aa 清账 [账单ID]\n示例：/aa 清账 abc123"
            return await self._clear_bill(event, args[0])
        
        # 帮助信息：/aa 帮助
        elif cmd == "帮助":
            return self._get_help_text()
        
        else:
            return f"❌ 未知命令：{cmd}\n{self._get_help_text()}"

    # ---------------------- 核心功能实现 ----------------------
    async def _create_bill(self, event: AstrMessageEvent, params: List[str]) -> str:
        """创建AA账单"""
        if len(params) < 2:
            return (
                "❌ 格式错误！正确用法：\n"
                "📌 简单模式：/aa [参与人] [金额]\n"
                "   示例：/aa 陈 100\n"
                "📌 完整模式：/aa [参与人1] [参与人2] ... [金额] [描述]\n"
                "   示例：/aa 张三 李四 600 聚餐"
            )

        # 解析金额（从后往前找第一个数字）
        try:
            amount = None
            amount_idx = -1
            for i in reversed(range(len(params))):
                try:
                    amount = float(params[i])
                    amount_idx = i
                    break
                except ValueError:
                    continue
            
            if amount is None or amount <= 0:
                return "❌ 金额错误！请输入有效的正数"

            # 提取参与人、金额、描述
            participants = params[:amount_idx]
            total_amount = round(amount, 2)
            description = " ".join(params[amount_idx+1:]) if (amount_idx+1 < len(params)) else "日常消费"
            
        except Exception as e:
            return f"❌ 解析失败：{str(e)}"

        # 补充付款人信息
        payer_id = event.get_sender_id()
        payer_name = event.get_sender_name() or f"用户{payer_id[:4]}"
        if payer_name not in participants:
            participants.append(payer_name)
        participants = list(set(participants))
        total_people = len(participants)

        # 计算分摊金额
        per_person = round(total_amount / total_people, 2)
        diff = round(total_amount - (per_person * total_people), 2)

        # 生成账单ID和时间
        bill_id = str(uuid.uuid4())[:6]
        create_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timestamp = int(time.time())

        # 构建账单信息
        bill = {
            "bill_id": bill_id,
            "payer": {"id": payer_id, "name": payer_name},
            "total_amount": total_amount,
            "description": description,
            "participants": participants,
            "total_people": total_people,
            "per_person": per_person,
            "diff": diff,
            "status": "pending",
            "create_time": create_time,
            "timestamp": timestamp,
            "clear_time": None,
            "clearer": None,
            "debts": self._gen_debts(payer_name, participants, per_person)
        }

        # 保存账单
        self.aa_bills.setdefault(payer_id, []).append(bill)
        self._save_persistent_data()

        # 生成结果
        result = (
            "✅ 账单创建成功！\n"
            "=" * 40 + "\n"
            f"🆔 账单ID：{bill_id}\n"
            f"💸 付款人：{payer_name}\n"
            f"📝 描述：{description}\n"
            f"💰 总金额：{total_amount}元\n"
            f"👥 参与人（{total_people}人）：{', '.join(participants)}\n"
            f"🧮 每人分摊：{per_person}元\n"
        )
        if diff > 0:
            result += f"⚠️ 分账误差：{payer_name}多承担{diff}元\n"
        result += (
            f"⏰ 时间：{create_time}\n"
            "=" * 40 + "\n"
            "💡 操作：\n"
            f"  查看所有账单：/aa 查\n"
            f"  标记清账：/aa 清账 {bill_id}\n"
            f"  查看明细：/aa 对账 {bill_id}"
        )
        return result

    async def _list_bills(self, event: AstrMessageEvent) -> str:
        """查看账单列表"""
        user_id = event.get_sender_id()
        bills = self.aa_bills.get(user_id, [])
        if not bills:
            return "📋 暂无账单\n💡 创建账单：/aa [参与人] [金额]（示例：/aa 陈 100）"

        # 排序并统计
        bills_sorted = sorted(bills, key=lambda x: x["timestamp"], reverse=True)[:10]
        pending = len([b for b in bills if b["status"] == "pending"])
        cleared = len(bills) - pending

        # 构建列表
        result = f"📊 账单列表（待清账：{pending} | 已清账：{cleared}）\n" + "-" * 50 + "\n"
        for i, bill in enumerate(bills_sorted, 1):
            status = "🔴 待清账" if bill["status"] == "pending" else "🟢 已清账"
            op = f"操作：/aa 清账 {bill['bill_id']}" if bill["status"] == "pending" else f"清账时间：{bill['clear_time']}"
            
            result += (
                f"{i}. ID：{bill['bill_id']} | {status}\n"
                f"   描述：{bill['description']}\n"
                f"   付款人：{bill['payer']['name']} | 金额：{bill['total_amount']}元\n"
                f"   参与人：{', '.join(bill['participants'])}\n"
                f"   时间：{bill['create_time']}\n"
                f"   {op}\n"
                "-" * 50 + "\n"
            )
        return result

    async def _show_debt(self, event: AstrMessageEvent, bill_id: str) -> str:
        """查看债务明细"""
        user_id = event.get_sender_id()
        for bill in self.aa_bills.get(user_id, []):
            if bill["bill_id"] == bill_id:
                status = "🔴 待清账" if bill["status"] == "pending" else "🟢 已清账"
                result = (
                    f"📊 账单「{bill_id}」明细 | {status}\n"
                    "=" * 40 + "\n"
                    f"📝 描述：{bill['description']}\n"
                    f"💸 付款人：{bill['payer']['name']}（垫付{bill['total_amount']}元）\n"
                    f"🧮 每人分摊：{bill['per_person']}元\n"
                    "\n【债务关系】\n"
                )
                for debt in bill["debts"]:
                    result += f"👉 {debt['debtor']} 应支付 {debt['creditor']} {debt['amount']}元\n"
                
                if bill["diff"] > 0:
                    result += (
                        f"\n⚠️ 误差说明：\n"
                        f"{bill['payer']['name']}多承担{bill['diff']}元（总金额无法均分）\n"
                    )
                if bill["status"] == "pending":
                    result += f"\n💡 标记清账：/aa 清账 {bill_id}\n"
                else:
                    result += f"\n✅ 清账时间：{bill['clear_time']}（{bill['clearer']['name']}）\n"
                return result
        
        return f"❌ 未找到账单ID「{bill_id}」\n💡 查看所有账单：/aa 查"

    async def _clear_bill(self, event: AstrMessageEvent, bill_id: str) -> str:
        """标记清账"""
        user_id = event.get_sender_id()
        clearer_name = event.get_sender_name() or f"用户{user_id[:4]}"
        clear_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for bill in self.aa_bills.get(user_id, []):
            if bill["bill_id"] == bill_id:
                if bill["status"] == "cleared":
                    return (
                        f"✅ 账单「{bill_id}」已清账\n"
                        f"清账时间：{bill['clear_time']}\n"
                        f"操作人：{bill['clearer']['name']}"
                    )
                
                # 更新账单状态
                bill["status"] = "cleared"
                bill["clear_time"] = clear_time
                bill["clearer"] = {"id": user_id, "name": clearer_name}
                
                # 记录清账
                self.settlement_records.setdefault(user_id, []).append({
                    "record_id": str(uuid.uuid4())[:8],
                    "bill_id": bill_id,
                    "description": bill["description"],
                    "amount": bill["total_amount"],
                    "clearer": {"id": user_id, "name": clearer_name},
                    "time": clear_time,
                    "timestamp": int(time.time())
                })
                
                self._save_persistent_data()
                return (
                    f"✅ 账单「{bill_id}」已标记为清账！\n"
                    "=" * 40 + "\n"
                    f"📝 描述：{bill['description']}\n"
                    f"💰 金额：{bill['total_amount']}元\n"
                    f"⏰ 时间：{clear_time}\n"
                    f"操作人：{clearer_name}\n"
                    "=" * 40
                )
        
        return f"❌ 未找到账单ID「{bill_id}」\n💡 查看所有账单：/aa 查"

    # ---------------------- 辅助方法 ----------------------
    def _gen_debts(self, payer: str, participants: List[str], amount: float) -> List[Dict]:
        """生成债务明细"""
        return [
            {"debtor": p, "creditor": payer, "amount": amount}
            for p in participants if p != payer
        ]

    def _get_help_text(self) -> str:
        """帮助信息"""
        return (
            "📊 AA记账机器人帮助\n"
            "=" * 40 + "\n"
            "【可用指令】\n"
            "1. 创建账单：\n"
            "   /aa [参与人1] [参与人2] ... [金额] [描述可选]\n"
            "   示例：/aa 陈 100 或 /aa 张三 李四 600 聚餐\n"
            "\n"
            "2. 查看所有账单：\n"
            "   /aa 查\n"
            "\n"
            "3. 查看债务明细：\n"
            "   /aa 对账 [账单ID]\n"
            "   示例：/aa 对账 abc123\n"
            "\n"
            "4. 标记账单清账：\n"
            "   /aa 清账 [账单ID]\n"
            "   示例：/aa 清账 abc123\n"
            "\n"
            "5. 查看帮助：\n"
            "   /aa 帮助\n"
            "=" * 40
        )

    # ---------------------- 数据持久化 ----------------------
    def _load_persistent_data(self):
        """加载账单和清账记录"""
        try:
            if os.path.exists(self.bills_path):
                with open(self.bills_path, "r", encoding="utf-8") as f:
                    self.aa_bills = json.load(f)
            if os.path.exists(self.records_path):
                with open(self.records_path, "r", encoding="utf-8") as f:
                    self.settlement_records = json.load(f)
        except Exception as e:
            logger.error(f"加载数据失败：{e}")
            self.aa_bills = {}
            self.settlement_records = {}

    def _save_persistent_data(self):
        """保存数据"""
        try:
            with open(self.bills_path, "w", encoding="utf-8") as f:
                json.dump(self.aa_bills, f, ensure_ascii=False, indent=2)
            with open(self.records_path, "w", encoding="utf-8") as f:
                json.dump(self.settlement_records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存数据失败：{e}")

    async def terminate(self):
        """插件卸载时保存数据"""
        self._save_persistent_data()
        logger.info("AA记账插件已卸载，数据已保存")
