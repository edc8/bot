from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from typing import Dict, List, Optional, Union
import json
import os
import time
import uuid

@register(
    "accounting", 
    "anchor",
    "简单记账机器人（含极简AA分账功能）",
    "1.3.7"  # 版本升级
)
class AccountingPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.user_records: Dict[str, List[Dict]] = {}
        self.aa_bills: Dict[str, Dict] = {}
        self.acc_data_path = os.path.join(os.path.dirname(__file__), "accounting_data.json")
        self.aa_data_path = os.path.join(os.path.dirname(__file__), "aa_bills_data.json")
        self._load_data()

    # 关键修复：兼容性空方法
    def _empty(self, *args, **kwargs):
        """框架要求的空方法"""
        pass

    # ---------------------- AA分账核心功能（已修复）---------------------
    @filter.command_group("ac")
    def accounting_main_group(self):
        pass

    @accounting_main_group.command("aa")
    async def handle_aa(self, event: AstrMessageEvent, *args):
        """修复后的AA分账入口"""
        if not args:
            yield event.plain_result("❌ 参数不足！格式：/ac aa 参与人 金额 或 /ac aa 对账")
            return

        if args[0] == "对账":
            await self._show_aa_bills(event)
        elif args[0] == "清账" and len(args) > 1:
            await self._clear_aa_bill(event, args[1])
        else:
            await self._create_aa_bill(event, *args)

    async def _create_aa_bill(self, event: AstrMessageEvent, *args):
        """AA账单创建（修复参数解析）"""
        try:
            # 参数验证
            if len(args) < 2:
                raise ValueError("至少需要1个参与人和金额")

            # 解析金额（最后一个参数）
            amount = float(args[-1])
            if amount <= 0:
                raise ValueError("金额必须>0")

            # 获取参与人（排除金额）
            participants = list(set(args[:-1]))  # 自动去重
            payer = event.get_sender_name() or f"用户{event.get_sender_id()[:4]}"
            if payer not in participants:
                participants.append(payer)

            # 计算分摊
            per_person = round(amount / len(participants), 2)
            bill_id = str(uuid.uuid4())[:6]  # 6位ID更易读

            # 生成记录
            records = self._generate_aa_records(
                event.get_sender_id(),
                payer,
                participants,
                amount,
                per_person,
                bill_id
            )

            # 保存数据
            self._save_data()
            
            yield event.plain_result(
                f"✅ AA分账成功！\n"
                f"ID: {bill_id} | 总金额: {amount}元\n"
                f"参与人: {', '.join(participants)}\n"
                f"每人应付: {per_person}元"
            )
        except Exception as e:
            yield event.plain_result(f"❌ 创建AA失败: {str(e)}")

    def _generate_aa_records(self, user_id, payer, participants, total_amount, per_person, bill_id):
        """生成AA相关记账记录（修复数据结构）"""
        # 付款人支出记录
        expense_record = {
            "id": str(uuid.uuid4())[:8],
            "type": "expense",
            "amount": total_amount,
            "category": "AA支出",
            "note": f"AA#{bill_id}",
            "time": time.strftime("%Y-%m-%d %H:%M"),
            "aa_bill_id": bill_id
        }

        # 应收记录（排除付款人）
        income_records = []
        for person in [p for p in participants if p != payer]:
            income_records.append({
                "id": str(uuid.uuid4())[:8],
                "type": "income",
                "amount": per_person,
                "source": "AA应收",
                "note": f"来自{person}",
                "time": time.strftime("%Y-%m-%d %H:%M"),
                "aa_bill_id": bill_id
            })

        # 保存记录
        self.user_records.setdefault(user_id, []).extend([expense_record] + income_records)
        
        # 保存AA账单
        self.aa_bills[bill_id] = {
            "id": bill_id,
            "payer": payer,
            "amount": total_amount,
            "per_person": per_person,
            "participants": participants,
            "status": "待清账",
            "time": time.time()
        }

    # ---------------------- 辅助功能 ---------------------
    async def _show_aa_bills(self, event: AstrMessageEvent):
        """对账功能（修复显示格式）"""
        if not self.aa_bills:
            yield event.plain_result("📭 暂无AA账单")
            return

        pending = [b for b in self.aa_bills.values() if b["status"] == "待清账"]
        output = ["📊 AA对账（待清账）"] + [
            f"{idx}. ID:{b['id']} 金额:{b['amount']}元\n  参与人:{', '.join(b['participants'])}"
            for idx, b in enumerate(pending[:5], 1)
        ]
        yield event.plain_result("\n".join(output))

    async def _clear_aa_bill(self, event: AstrMessageEvent, bill_id: str):
        """清账功能（修复状态更新）"""
        if bill_id not in self.aa_bills:
            yield event.plain_result(f"❌ 账单ID不存在")
            return

        self.aa_bills[bill_id]["status"] = "已清账"
        self.aa_bills[bill_id]["clear_time"] = time.time()
        self._save_data()
        yield event.plain_result(f"✅ 账单 {bill_id} 已标记为已清账")

    # ---------------------- 数据操作 ---------------------
    def _load_data(self):
        """合并数据加载"""
        for path, target in [
            (self.acc_data_path, "user_records"),
            (self.aa_data_path, "aa_bills")
        ]:
            try:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        setattr(self, target, json.load(f))
            except Exception as e:
                logger.error(f"加载{target}失败: {str(e)}")
                setattr(self, target, {})

    def _save_data(self):
        """合并数据保存"""
        for path, data in [
            (self.acc_data_path, self.user_records),
            (self.aa_data_path, self.aa_bills)
        ]:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"保存数据失败: {str(e)}")
