from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from typing import Dict, List, Optional
import json
import os
import time
import uuid


@register(
    "accounting",  # 插件名称（必填）
    "anchor",      # 作者（必填）
    "简单记账机器人（含AA分账）",  # 描述（必填）
    "1.4.0"        # 版本（必填）
)
class AccountingPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 记账数据：{用户ID: [记录列表]}
        self.user_records: Dict[str, List[Dict]] = {}
        # AA账单数据：{账单ID: 账单详情}
        self.aa_bills: Dict[str, List[Dict]] = {}  # 修正：统一用列表存储，避免字典嵌套问题
        # 数据存储路径
        self.acc_data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounting_data.json")
        self.aa_data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aa_bills_data.json")
        # 加载历史数据
        self._load_accounting_data()
        self._load_aa_data()

    # ---------------------- 修复核心：正确定义 _empty() 方法 ----------------------
    def _empty(self):
        """框架默认调用的占位方法，仅含 self 参数（必须保留，避免报错）"""
        pass

    # ---------------------- 主指令组 ----------------------
    @filter.command_group("ac")
    def accounting_main_group(self):
        """记账主指令组（含AA分账）"""
        pass

    # ---------------------- 基础记账功能（保障AA分账依赖） ----------------------
    @accounting_main_group.command("help")
    async def show_help(self, event: AstrMessageEvent):
        """显示帮助（含AA分账用法）"""
        help_text = (
            "📊 记账机器人帮助（v1.4.0 · 修复版）\n"
            "====================\n"
            "【基础记账】\n"
            "/ac + [金额] [来源] [备注] - 加收入（例：/ac + 5000 工资 6月）\n"
            "/ac - [金额] [分类] [备注] - 加支出（例：/ac - 25 餐饮 午餐）\n"
            "/ac 查       - 看最近10条记录\n"
            "/ac 汇总     - 看收支总览\n"
            "/ac 删 [ID]  - 删除记录（ID从“查”获取）\n"
            "\n【AA分账（核心功能）】\n"
            "1. 创建AA账单：/ac aa [参与人1] [参与人2] [金额]（例：/ac aa 张三 李四 300）\n"
            "2. 查看AA账单：/ac aa 对账（区分待清账/已清账）\n"
            "3. 标记清账：/ac aa 清账 [账单ID]（例：/ac aa 清账 a1b2）\n"
            "====================\n"
            "💡 提示：AA账单ID为4位短码，金额支持小数（如29.5）"
        )
        yield event.plain_result(help_text)

    @accounting_main_group.command("+")
    async def add_income(self, event: AstrMessageEvent, amount: str, source: str, note: str = ""):
        """添加收入（AA分账的“应收”记录依赖此方法逻辑）"""
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
        """添加支出（AA分账的“付款”记录依赖此方法逻辑）"""
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
    async def list_records(self, event: AstrMessageEvent):
        """查看记账记录（含AA分账生成的记录）"""
        user_id = event.get_sender_id()
        records = self.user_records.get(user_id, [])
        if not records:
            yield event.plain_result("📒 暂无记账记录（可先用“/ac aa 张三 100”创建AA账单）")
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
    async def show_summary(self, event: AstrMessageEvent):
        """收支汇总（含AA分账的收支）"""
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

    @accounting_main_group.command("删")
    async def delete_record(self, event: AstrMessageEvent, record_id: str):
        """删除记账记录（含AA分账生成的记录）"""
        user_id = event.get_sender_id()
        records = self.user_records.get(user_id, [])
        for idx, rec in enumerate(records):
            if rec["id"] == record_id:
                records.pop(idx)
                self._save_accounting_data()
                type_str = "收入" if rec["type"] == "income" else "支出"
                yield event.plain_result(f"✅ 已删除{type_str}记录：{rec['amount']}")
                return
        yield event.plain_result(f"❌ 未找到ID为「{record_id}」的记录（用“/ac 查”确认ID）")

    # ---------------------- AA分账核心功能（修复后） ----------------------
    @accounting_main_group.command("aa")
    async def handle_aa(self, event: AstrMessageEvent, *args):
        """
        AA分账总指令：支持创建账单、对账、清账
        调用逻辑：根据参数自动识别操作类型
        """
        user_id = event.get_sender_id()
        current_user = event.get_sender_name() or f"用户{user_id[:4]}"  # 当前用户昵称
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        current_timestamp = int(time.time())

        # 操作1：AA对账（参数为 ["对账"]）
        if args and args[0] == "对账":
            async for res in self._aa_check(event):
                yield res
            return

        # 操作2：AA清账（参数为 ["清账", "账单ID"]）
        if len(args) >= 2 and args[0] == "清账":
            bill_id = args[1]
            async for res in self._aa_clear(event, bill_id, current_time):
                yield res
            return

        # 操作3：创建AA账单（参数为 ["参与人1", "参与人2", ..., "金额"]）
        if len(args) < 2:
            yield event.plain_result(
                "❌ AA指令格式错误！正确用法：\n"
                "1. 创建AA：/ac aa 参与人1 参与人2 金额（例：/ac aa 张三 李四 300）\n"
                "2. 对账：/ac aa 对账\n"
                "3. 清账：/ac aa 清账 账单ID（例：/ac aa 清账 a1b2）"
            )
            return

        # 解析AA账单参数（最后1个是金额，前面是参与人）
        amount_str = args[-1]
        participants = [p.strip() for p in args[:-1] if p.strip()]  # 去重前处理空字符串

        # 验证金额有效性
        try:
            total_amount = float(amount_str)
            if total_amount <= 0:
                raise ValueError("AA金额必须大于0")
        except ValueError:
            yield event.plain_result(f"❌ 金额错误：请输入数字（如100或258.5）")
            return

        # 处理参与人（去重+自动加入当前用户）
        participants = list(set(participants))  # 去重
        if current_user not in participants:
            participants.append(current_user)  # 确保创建者在参与人中
        total_people = len(participants)
        per_person = round(total_amount / total_people, 2)  # 人均金额（保留2位小数）

        # 处理分账误差（总金额可能≠人均×人数，误差加给当前用户）
        total_calculated = round(per_person * total_people, 2)
        diff = round(total_amount - total_calculated, 2)
        payer_amount = per_person + diff if diff != 0 else per_person

        # 生成4位短账单ID（易记，避免用户输入负担）
        bill_id = str(uuid.uuid4())[:4]

        # 步骤1：生成AA账单记录（用于对账和清账）
        aa_bill = {
            "bill_id": bill_id,
            "creator": current_user,
            "total_amount": round(total_amount, 2),
            "per_person": per_person,
            "participants": participants,
            "status": "待清账",  # 状态：待清账/已清账
            "create_time": current_time,
            "clear_time": None,
            "user_id": user_id  # 绑定创建者ID，避免跨用户查看
        }
        self.aa_bills.setdefault(user_id, []).append(aa_bill)
        self._save_aa_data()

        # 步骤2：生成关联的记账记录（自动同步到基础记账）
        # 2.1 付款人（当前用户）生成“AA支出”记录
        expense_id = str(uuid.uuid4())[:8]
        expense_record = {
            "id": expense_id,
            "type": "expense",
            "amount": round(total_amount, 2),
            "category": "AA制支出",
            "note": f"AA账单-{bill_id}-{', '.join(participants)}",
            "create_time": current_time,
            "timestamp": current_timestamp
        }
        self.user_records.setdefault(user_id, []).append(expense_record)

        # 2.2 其他参与人生成“AA应收”收入记录
        for person in participants:
            if person == current_user:
                continue  # 跳过自己
            income_id = str(uuid.uuid4())[:8]
            income_record = {
                "id": income_id,
                "type": "income",
                "amount": per_person,
                "source": "AA制应收",
                "note": f"AA账单-{bill_id}-来自{person}",
                "create_time": current_time,
                "timestamp": current_timestamp
            }
            self.user_records.setdefault(user_id, []).append(income_record)

        # 保存记账数据
        self._save_accounting_data()

        # 返回AA创建结果
        yield event.plain_result(
            f"✅ AA账单创建成功！\n"
            f"🆔 账单ID：{bill_id}（清账用）\n"
            f"💵 总金额：{total_amount}元（{total_people}人平摊）\n"
            f"👥 参与人：{', '.join(participants)}\n"
            f"💸 每人：{per_person}元（你多承担{diff}元误差）\n"
            f"⏰ 时间：{current_time}\n"
            f"📜 已生成{1 + len(participants)-1}条记账记录（用“/ac 查”查看）\n"
            f"下一步：对方付款后执行「/ac aa 清账 {bill_id}」"
        )

    # ---------------------- AA分账辅助方法 ----------------------
    async def _aa_check(self, event: AstrMessageEvent):
        """AA对账：查看当前用户的所有AA账单"""
        user_id = event.get_sender_id()
        aa_bills = self.aa_bills.get(user_id, [])
        if not aa_bills:
            yield event.plain_result("📋 暂无AA账单（用“/ac aa 张三 100”创建）")
            return

        # 按创建时间倒序（最新在前）
        sorted_bills = sorted(aa_bills, key=lambda x: x["create_time"], reverse=True)
        pending_bills = [b for b in sorted_bills if b["status"] == "待清账"]
        cleared_bills = [b for b in sorted_bills if b["status"] == "已清账"]

        # 构建对账输出
        output = "📊 AA账单对账记录\n"
        output += "========================================\n"

        # 待清账账单（优先显示）
        if pending_bills:
            output += f"🔴 待清账（{len(pending_bills)}条）\n"
            output += "----------------------------------------\n"
            for bill in pending_bills[:5]:  # 最多显示5条
                output += (
                    f"ID: {bill['bill_id']} | 金额: {bill['total_amount']}元\n"
                    f"参与: {', '.join(bill['participants'])} | 每人: {bill['per_person']}元\n"
                    f"时间: {bill['create_time']} | 操作: /ac aa 清账 {bill['bill_id']}\n"
                    "----------------------------------------\n"
                )

        # 已清账账单
        if cleared_bills:
            output += f"🟢 已清账（{len(cleared_bills)}条）\n"
            output += "----------------------------------------\n"
            for bill in cleared_bills[:3]:  # 最多显示3条
                output += (
                    f"ID: {bill['bill_id']} | 金额: {bill['total_amount']}元\n"
                    f"参与: {', '.join(bill['participants'])} | 清账时间: {bill['clear_time']}\n"
                    "----------------------------------------\n"
                )

        output += f"📝 总计：共{len(sorted_bills)}条（待清账{len(pending_bills)}条）"
        yield event.plain_result(output)

    async def _aa_clear(self, event: AstrMessageEvent, bill_id: str, clear_time: str):
        """AA清账：标记账单为已清账"""
        user_id = event.get_sender_id()
        aa_bills = self.aa_bills.get(user_id, [])
        if not aa_bills:
            yield event.plain_result("📋 暂无AA账单，无需清账")
            return

        # 查找待清账账单
        target_bill = None
        for bill in aa_bills:
            if bill["bill_id"] == bill_id and bill["status"] == "待清账":
                target_bill = bill
                break

        if not target_bill:
            yield event.plain_result(
                f"❌ 清账失败：未找到ID为「{bill_id}」的待清账账单\n"
                f"提示：用“/ac aa 对账”查看所有有效账单ID"
            )
            return

        # 更新账单状态
        target_bill["status"] = "已清账"
        target_bill["clear_time"] = clear_time
        self.aa_bills[user_id] = aa_bills
        self._save_aa_data()

        # 返回清账结果
        yield event.plain_result(
            f"✅ AA账单「{bill_id}」已清账！\n"
            f"💵 金额：{target_bill['total_amount']}元\n"
            f"👥 参与人：{', '.join(target_bill['participants'])}\n"
            f"⏰ 清账时间：{clear_time}\n"
            f"📌 提示：记账记录已保留，可通过“/ac 查”查看历史"
        )

    # ---------------------- 数据加载/保存（保障AA数据持久化） ----------------------
    def _load_accounting_data(self):
        """加载基础记账数据"""
        try:
            if os.path.exists(self.acc_data_path):
                with open(self.acc_data_path, "r", encoding="utf-8") as f:
                    self.user_records = json.load(f)
            logger.info(f"加载记账数据成功（共{sum(len(v) for v in self.user_records.values())}条记录）")
        except Exception as e:
            self.user_records = {}
            logger.error(f"加载记账数据失败：{str(e)}（已初始化空数据）")

    def _save_accounting_data(self):
        """保存基础记账数据"""
        try:
            with open(self.acc_data_path, "w", encoding="utf-8") as f:
                json.dump(self.user_records, f, ensure_ascii=False, indent=2)
            logger.info(f"保存记账数据成功（共{sum(len(v) for v in self.user_records.values())}条记录）")
        except Exception as e:
            logger.error(f"保存记账数据失败：{str(e)}")

    def _load_aa_data(self):
        """加载AA账单数据"""
        try:
            if os.path.exists(self.aa_data_path):
                with open(self.aa_data_path, "r", encoding="utf-8") as f:
                    self.aa_bills = json.load(f)
            logger.info(f"加载AA数据成功（共{sum(len(v) for v in self.aa_bills.values())}个账单）")
        except Exception as e:
            self.aa_bills = {}
            logger.error(f"加载AA数据失败：{str(e)}（已初始化空数据）")

    def _save_aa_data(self):
        """保存AA账单数据"""
        try:
            with open(self.aa_data_path, "w", encoding="utf-8") as f:
                json.dump(self.aa_bills, f, ensure_ascii=False, indent=2)
            logger.info(f"保存AA数据成功（共{sum(len(v) for v in self.aa_bills.values())}个账单）")
        except Exception as e:
            logger.error(f"保存AA数据失败：{str(e)}")

    # ---------------------- 插件卸载清理 ----------------------
    async def terminate(self):
        """插件卸载时保存所有数据，避免丢失"""
        self._save_accounting_data()
        self._save_aa_data()
        logger.info("记账机器人插件（v1.4.0）已卸载，数据已保存")
