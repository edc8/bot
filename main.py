from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from typing import Dict, List, Optional, Union
import json
import os
import time
import uuid


@register(
    plugin_name="accounting",
    author="anchor",
    description="简单记账机器人（极简AA分账：/ac aa 参与人1 参与人2 金额）",
    version="1.3.0",
    repo_url="https://github.com/anchorAnc/astrbot_plugin_accounting"
)
class AccountingPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.user_records: Dict[str, List[Dict]] = {}  # 记账记录
        self.aa_bills: Dict[str, Dict] = {}            # AA账单（用于对账/清账）
        # 数据路径
        self.acc_data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounting_data.json")
        self.aa_data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aa_bills_data.json")
        # 加载数据
        self._load_accounting_data()
        self._load_aa_data()

    # ---------------------- 主指令组 ----------------------
    @filter.command_group("ac")
    def accounting_main_group(self):
        """记账主指令组"""
        pass

    # ---------------------- 基础记账功能（保留，优化帮助） ----------------------
    @accounting_main_group.command("help")
    async def show_help(self, event: AstrMessageEvent):
        """显示帮助（突出极简AA操作）"""
        help_text = (
            "📊 记账机器人帮助（v1.3.0 · 极简AA版）\n"
            "====================\n"
            "【基础记账】\n"
            "/ac + [金额] [来源] [备注] - 加收入（例：/ac + 5000 工资 6月）\n"
            "/ac - [金额] [分类] [备注] - 加支出（例：/ac - 25 餐饮 午餐）\n"
            "/ac 查       - 看最近10条记录\n"
            "/ac 汇总     - 看收支总览\n"
            "/ac 分类     - 看支出统计\n"
            "/ac 删 [ID]  - 删除记录\n"
            "\n【极简AA分账（1步完成）】\n"
            "✅ 核心指令：/ac aa [参与人1] [参与人2] ... [金额]\n"
            "   例1（2人）：/ac aa 张三 100 → 你和张三平摊100元\n"
            "   例2（3人）：/ac aa 张三 李四 300 → 3人平摊300元\n"
            "\n【AA辅助操作】\n"
            "/ac aa 对账     - 查看所有AA账单（待清账/已清账）\n"
            "/ac aa 清账 [ID] - 标记AA账单为已清账（ID从对账获取）\n"
            "====================\n"
            "💡 提示：AA默认你是付款人，自动计算人均金额并生成记账记录"
        )
        yield event.plain_result(help_text)

    @accounting_main_group.command("+")
    async def add_income(self, event: AstrMessageEvent, amount: str, source: str, note: str = ""):
        user_id = event.get_sender_id()
        try:
            amount_val = float(amount)
            if amount_val <= 0:
                raise ValueError("金额必须大于0")
        except ValueError as e:
            yield event.plain_result(f"❌ 收入添加失败：{str(e)}")
            return

        timestamp = int(time.time())
        record = {
            "id": str(uuid.uuid4())[:8],
            "type": "income",
            "amount": round(amount_val, 2),
            "source": source,
            "note": note.strip(),
            "create_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)),
            "timestamp": timestamp
        }

        self.user_records.setdefault(user_id, []).append(record)
        self._save_accounting_data()
        yield event.plain_result(
            f"✅ 收入添加成功！\n"
            f"金额：{record['amount']} | 来源：{source}\n"
            f"时间：{record['create_time']} | ID：{record['id']}"
        )

    @accounting_main_group.command("-")
    async def add_expense(self, event: AstrMessageEvent, amount: str, category: str, note: str = ""):
        user_id = event.get_sender_id()
        try:
            amount_val = float(amount)
            if amount_val <= 0:
                raise ValueError("金额必须大于0")
        except ValueError as e:
            yield event.plain_result(f"❌ 支出添加失败：{str(e)}")
            return

        timestamp = int(time.time())
        record = {
            "id": str(uuid.uuid4())[:8],
            "type": "expense",
            "amount": round(amount_val, 2),
            "category": category,
            "note": note.strip(),
            "create_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)),
            "timestamp": timestamp
        }

        self.user_records.setdefault(user_id, []).append(record)
        self._save_accounting_data()
        yield event.plain_result(
            f"✅ 支出添加成功！\n"
            f"金额：{record['amount']} | 分类：{category}\n"
            f"时间：{record['create_time']} | ID：{record['id']}"
        )

    @accounting_main_group.command("查")
    async def list_recent_records(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        records = self.user_records.get(user_id, [])
        if not records:
            yield event.plain_result("📒 暂无记账记录")
            return

        sorted_records = sorted(records, key=lambda x: x["timestamp"], reverse=True)[:10]
        output = f"📜 最近{len(sorted_records)}条记录（共{len(records)}条）：\n"
        for idx, rec in enumerate(sorted_records, 1):
            type_tag = "💵 收入" if rec["type"] == "income" else "💸 支出"
            type_extra = f"来源：{rec['source']}" if rec["type"] == "income" else f"分类：{rec['category']}"
            output += (
                f"{idx}. {type_tag} | 金额：{rec['amount']}\n"
                f"   {type_extra} | 备注：{rec['note'] or '无'}\n"
                f"   时间：{rec['create_time']} | ID：{rec['id']}\n"
            )
        yield event.plain_result(output)

    @accounting_main_group.command("汇总")
    async def show_finance_summary(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        records = self.user_records.get(user_id, [])
        if not records:
            yield event.plain_result("📒 暂无记账记录")
            return

        total_income = round(sum(r["amount"] for r in records if r["type"] == "income"), 2)
        total_expense = round(sum(r["amount"] for r in records if r["type"] == "expense"), 2)
        balance = round(total_income - total_expense, 2)

        output = f"📊 收支汇总：\n"
        output += f"💵 总收入：{total_income} | 💸 总支出：{total_expense}\n"
        output += f"📈 结余：{balance}"
        yield event.plain_result(output)

    @accounting_main_group.command("分类")
    async def show_expense_categories(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        expenses = [r for r in self.user_records.get(user_id, []) if r["type"] == "expense"]
        if not expenses:
            yield event.plain_result("📒 暂无支出记录")
            return

        category_stats = {}
        for exp in expenses:
            category_stats[exp["category"]] = category_stats.get(exp["category"], 0.0) + exp["amount"]
        sorted_cats = sorted(category_stats.items(), key=lambda x: x[1], reverse=True)
        total_exp = sum(category_stats.values())

        output = f"📊 支出分类统计：\n"
        for cat, amt in sorted_cats[:5]:
            output += f"• {cat}：{round(amt, 2)}（{round(amt/total_exp*100,1)}%）\n"
        if len(sorted_cats) > 5:
            output += f"• 其他分类：{round(total_exp-sum(amt for cat, amt in sorted_cats[:5]),2)}"
        yield event.plain_result(output)

    @accounting_main_group.command("删")
    async def delete_record(self, event: AstrMessageEvent, record_id: str):
        user_id = event.get_sender_id()
        records = self.user_records.get(user_id, [])
        for idx, rec in enumerate(records):
            if rec["id"] == record_id:
                records.pop(idx)
                self._save_accounting_data()  # 修复原代码调用错误：save_data() → _save_accounting_data()
                type_str = "收入" if rec["type"] == "income" else "支出"
                yield event.plain_result(f"✅ 已删除{type_str}记录：{rec['amount']}")
                return
        yield event.plain_result(f"❌ 未找到ID为「{record_id}」的记录")

    # ---------------------- 核心修改：极简AA分账（合并创建+分账） ----------------------
    @accounting_main_group.command("aa")
    async def handle_aa_all_in_one(self, event: AstrMessageEvent, *args):
        """
        极简AA分账：1步完成创建+分账
        支持3种操作：
        1. /ac aa 参与人1 参与人2 金额 → 创建并分账
        2. /ac aa 对账 → 查看所有AA账单
        3. /ac aa 清账 账单ID → 标记已清账
        """
        user_id = event.get_sender_id()
        current_user = event.get_sender_name() or f"用户{user_id[:4]}"  # 当前用户（默认付款人）
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        current_timestamp = int(time.time())

        # 操作1：AA对账
        if args and args[0] == "对账":
            await self._show_aa_bills(event)
            return

        # 操作2：AA清账
        if len(args) >= 2 and args[0] == "清账":
            bill_id = args[1]
            await self._clear_aa_bill(event, bill_id, current_time)
            return

        # 操作3：创建+分账（最少需要1个参与人+金额，如 /ac aa 张三 100）
        if len(args) < 2:
            yield event.plain_result(
                "❌ AA指令格式错误！正确用法：\n"
                "1. 分账：/ac aa 参与人1 参与人2 金额（例：/ac aa 张三 李四 300）\n"
                "2. 对账：/ac aa 对账\n"
                "3. 清账：/ac aa 清账 账单ID（例：/ac aa 清账 a1b2c3）"
            )
            return

        # 解析参数：最后1个是金额，前面是参与人
        amount_str = args[-1]
        participants = list(args[:-1])

        # 验证金额
        try:
            total_amount = float(amount_str)
            if total_amount <= 0:
                raise ValueError("金额必须大于0")
        except ValueError:
            yield event.plain_result(f"❌ 金额错误：请输入数字（如100或250.5）")
            return

        # 自动加入当前用户（避免漏加自己）
        if current_user not in participants:
            participants.append(current_user)
        participants = list(set(participants))  # 去重
        total_people = len(participants)
        per_person = round(total_amount / total_people, 2)

        # 处理分账误差（确保总金额=人均×人数，误差加给付款人）
        total_calculated = round(per_person * total_people, 2)
        diff = round(total_amount - total_calculated, 2)
        payer_actual = per_person + diff if diff != 0 else per_person

        # 生成4位短账单ID（易记）
        bill_id = str(uuid.uuid4())[:4]

        # 1. 生成记账记录（付款人支出+其他人应收）
        # 1.1 付款人（当前用户）支出记录
        expense_id = str(uuid.uuid4())[:8]
        expense_record = {
            "id": expense_id,
            "type": "expense",
            "amount": round(total_amount, 2),
            "category": "AA制支出",
            "note": f"AA分账-{bill_id}-{', '.join(participants)}",
            "create_time": current_time,
            "timestamp": current_timestamp,
            "aa_bill_id": bill_id
        }
        self.user_records.setdefault(user_id, []).append(expense_record)

        # 1.2 其他参与人应收记录（记为收入）
        income_records = []
        other_people = [p for p in participants if p != current_user]
        for person in other_people:
            income_id = str(uuid.uuid4())[:8]
            income_record = {
                "id": income_id,
                "type": "income",
                "amount": per_person,
                "source": "AA制应收",
                "note": f"AA分账-{bill_id}-来自{person}",
                "create_time": current_time,
                "timestamp": current_timestamp,
                "aa_bill_id": bill_id
            }
            self.user_records.setdefault(user_id, []).append(income_record)
            income_records.append({"person": person, "id": income_id, "amount": per_person})

        # 2. 保存AA账单（用于对账/清账）
        self.aa_bills[bill_id] = {
            "id": bill_id,
            "total_amount": round(total_amount, 2),
            "per_person": per_person,
            "payer": current_user,
            "participants": participants,
            "status": "待清账",
            "create_time": current_time,
            "clear_time": None,
            "related_records": {
                "expense_id": expense_id,
                "income_records": income_records
            }
        }

        # 3. 保存所有数据
        self._save_accounting_data()
        self._save_aa_data()

        # 4. 返回结果
        result = (
            f"✅ AA分账完成！\n"
            f"🆔 账单ID：{bill_id}\n"
            f"💵 总金额：{total_amount}元（{total_people}人平摊）\n"
            f"👥 参与人：{', '.join(participants)}\n"
            f"💸 每人：{per_person}元"
        )
        if diff != 0:
            result += f"（你多承担{diff}元误差）"
        result += (
            f"\n📜 生成记账记录：\n"
            f"• 你支出：{total_amount}元（ID：{expense_id}）\n"
        )
        for rec in income_records[:2]:  # 最多显示2条应收记录
            result += f"• 应收{rec['person']}：{rec['amount']}元（ID：{rec['id']}）\n"
        if len(income_records) > 2:
            result += f"• ... 共{len(income_records)}条应收记录\n"
        result += f"⏰ 操作：/ac aa 清账 {bill_id}（对方付款后标记）"
        yield event.plain_result(result)

    # ---------------------- AA辅助功能（对账/清账） ----------------------
    async def _show_aa_bills(self, event: AstrMessageEvent):
        """查看所有AA账单（区分待清账/已清账）"""
        if not self.aa_bills:
            yield event.plain_result("📋 暂无AA账单\n创建AA：/ac aa 参与人 金额（例：/ac aa 张三 100）")
            return

        # 按时间倒序排列
        sorted_bills = sorted(self.aa_bills.values(), key=lambda x: x["create_time"], reverse=True)
        pending = [b for b in sorted_bills if b["status"] == "待清账"]
        cleared = [b for b in sorted_bills if b["status"] == "已清账"]

        output = "📊 AA对账记录\n"
        output += "========================================\n"

        # 待清账（优先显示）
        if pending:
            output += f"🔴 待清账（{len(pending)}条）\n"
            output += "----------------------------------------\n"
            for bill in pending[:5]:  # 最多显示5条
                output += (
                    f"ID: {bill['id']} | 金额: {bill['total_amount']}元\n"
                    f"参与: {', '.join(bill['participants'])} | 每人: {bill['per_person']}元\n"
                    f"时间: {bill['create_time']} | 操作: /ac aa 清账 {bill['id']}\n"
                    "----------------------------------------\n"
                )

        # 已清账
        if cleared:
            output += f"🟢 已清账（{len(cleared)}条）\n"
            output += "----------------------------------------\n"
            for bill in cleared[:3]:  # 最多显示3条
                output += (
                    f"ID: {bill['id']} | 金额: {bill['total_amount']}元\n"
                    f"参与: {', '.join(bill['participants'])} | 清账时间: {bill['clear_time']}\n"
                    "----------------------------------------\n"
                )

        output += f"📝 总计：共{len(sorted_bills)}条（待清账{len(pending)}条）"
        yield event.plain_result(output)

    async def _clear_aa_bill(self, event: AstrMessageEvent, bill_id: str, clear_time: str):
        """标记AA账单为已清账"""
        if bill_id not in self.aa_bills:
            yield event.plain_result(f"❌ 未找到ID为「{bill_id}」的AA账单\n用 /ac aa 对账 查看所有ID")
            return

        bill = self.aa_bills[bill_id]
        if bill["status"] == "已清账":
            yield event.plain_result(f"✅ 账单「{bill_id}」已是已清账状态\n清账时间：{bill['clear_time']}")
            return

        # 更新账单状态
        bill["status"] = "已清账"
        bill["clear_time"] = clear_time
        self.aa_bills[bill_id] = bill
        self._save_aa_data()

        yield event.plain_result(
            f"✅ 账单「{bill_id}」已标记为清账\n"
            f"金额: {bill['total_amount']}元 | 参与人: {', '.join(bill['participants'])}\n"
            f"清账时间: {clear_time}"
        )

    # ---------------------- 辅助方法（数据加载/保存） ----------------------
    def _load_accounting_data(self):
        try:
            if os.path.exists(self.acc_data_path):
                with open(self.acc_data_path, "r", encoding="utf-8") as f:
                    self.user_records = json.load(f)
        except Exception as e:
            self.user_records = {}
            logger.error(f"加载记账数据失败：{str(e)}")

    def _save_accounting_data(self):
        try:
            with open(self.acc_data_path, "w", encoding="utf-8") as f:
                json.dump(self.user_records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存记账数据失败：{str(e)}")

    def _load_aa_data(self):
        try:
            if os.path.exists(self.aa_data_path):
                with open(self.aa_data_path, "r", encoding="utf-8") as f:
                    self.aa_bills = json.load(f)
        except Exception as e:
            self.aa_bills = {}
            logger.error(f"加载AA数据失败：{str(e)}")

    def _save_aa_data(self):
        try:
            with open(self.aa_data_path, "w", encoding="utf-8") as f:
                json.dump(self.aa_bills, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存AA数据失败：{str(e)}")

    async def terminate(self):
        self._save_accounting_data()
        self._save_aa_data()
        logger.info("记账插件（v1.3.0 极简AA版）已卸载，数据已保存")
