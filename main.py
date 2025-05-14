from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.event import MessageChain
from typing import Dict, List, Tuple, Optional
import json
import os
import time

@register("accounting", "anchor", "简单的记账机器人", "1.0.0", "https://github.com/anchorAnc/astrbot_plugin_accounting")
class AccountingPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 用户记账数据结构: {用户ID: 记账记录列表}
        self.user_records: Dict[str, List[Dict]] = {}
        # 插件数据存储路径
        self.data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounting_data.json")
        # 加载已保存的数据
        self.load_data()

    @filter.command_group("ac")
    def accounting(self):
        """记账指令组"""
        pass

    @accounting.command("help")
    async def show_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = (
            "📊 记账机器人帮助\n"
            "====================\n"
            "/ac + [金额] [来源] [备注(可选)] - 添加收入\n"
            "/ac - [金额] [分类] [备注(可选)] - 添加支出\n"
            "/ac 查 - 查看最近10条记录\n"
            "/ac 汇总 - 查看收支汇总信息\n"
            "/ac 分类 - 查看支出分类统计\n"
            "/ac 收入分类 - 查看收入分类统计\n"
            "/ac 删 [记录ID] - 删除记录\n"
            "/ac 帮助 - 显示本帮助\n"
            "====================\n"
            "示例:\n"
            "/ac + 5000 工资 6月工资\n"
            "/ac - 25 餐饮 午餐"
        )
        yield event.plain_result(help_text)

    @accounting.command("+")
    async def add_income(self, event: AstrMessageEvent, amount: str, source: str, note: str = ""):
        """添加收入记录"""
        user_id = event.get_sender_id()
        try:
            amount_value = float(amount)
            if amount_value <= 0:
                raise ValueError("金额必须大于0")
        except ValueError as e:
            yield event.plain_result(f"错误: {str(e)}")
            return

        # 记录时间戳
        timestamp = int(time.time())

        # 创建记录
        record_id = self.generate_record_id(user_id)
        record = {
            "id": record_id,
            "type": "income",
            "amount": amount_value,
            "source": source,
            "note": note,
            "timestamp": timestamp
        }

        # 添加到记录列表
        self.add_record(user_id, record)

        # 保存数据
        self.save_data()

        # 返回确认信息
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        yield event.plain_result(f"📝 收入记录已添加\n"
                                f"金额: {amount_value}\n"
                                f"来源: {source}\n"
                                f"备注: {note if note else '无'}\n"
                                f"时间: {time_str}")

    @accounting.command("-")
    async def add_expense(self, event: AstrMessageEvent, amount: str, category: str, note: str = ""):
        """添加支出记录"""
        user_id = event.get_sender_id()
        try:
            amount_value = float(amount)
            if amount_value <= 0:
                raise ValueError("金额必须大于0")
        except ValueError as e:
            yield event.plain_result(f"错误: {str(e)}")
            return

        # 记录时间戳
        timestamp = int(time.time())

        # 创建记录
        record_id = self.generate_record_id(user_id)
        records = self.user_records.get(user_id, [])
        record = {
            "id": record_id,
            "type": "expense",
            "amount": amount_value,
            "category": category,
            "note": note,
            "timestamp": timestamp
        }

        # 添加到记录列表
        records.append(record)
        self.user_records[user_id] = records

        # 保存数据
        self.save_data()

        # 返回确认信息
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        yield event.plain_result(f"📝 支出记录已添加\n"
                                f"金额: {amount_value}\n"
                                f"分类: {category}\n"
                                f"备注: {note if note else '无'}\n"
                                f"时间: {time_str}")

    @accounting.command("查")
    async def list_records(self, event: AstrMessageEvent):
        """查看最近的记账记录"""
        user_id = event.get_sender_id()
        records = self.user_records.get(user_id, [])
        count_value = 10

        if not records:
            yield event.plain_result("📒 没有记账记录")
            return

        # 按时间倒序排列
        sorted_records = sorted(records, key=lambda x: x["timestamp"], reverse=True)

        # 限制数量
        recent_records = sorted_records[:count_value]

        # 构建输出
        output = f"📒 最近 {len(recent_records)} 条记录:\n"
        for record in recent_records:
            time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record["timestamp"]))
            if record["type"] == "income":
                output += f"• [{record['id']}] 收入 {record['amount']} - {record['source']}"
                if record["note"]:
                    output += f" ({record['note']})"
                output += f" - {time_str}\n"
            else:
                output += f"• [{record['id']}] 支出 {record['amount']} - {record['category']}"
                if record["note"]:
                    output += f" ({record['note']})"
                output += f" - {time_str}\n"

        yield event.plain_result(output)

    @accounting.command("汇总")
    async def show_summary(self, event: AstrMessageEvent):
        """查看收支汇总信息"""
        user_id = event.get_sender_id()
        records = self.user_records.get(user_id, [])

        if not records:
            yield event.plain_result("📒 没有记账记录")
            return

        # 计算总收入、总支出和结余
        total_income = sum(record["amount"] for record in records if record["type"] == "income")
        total_expense = sum(record["amount"] for record in records if record["type"] == "expense")
        balance = total_income - total_expense

        # 构建输出
        output = f"📊 收支汇总信息:\n"
        output += f"📅 记录数量: {len(records)}\n"
        output += f"💵 总收入: {total_income}\n"
        output += f"💸 总支出: {total_expense}\n"
        output += f"📈 结余: {balance}\n"

        yield event.plain_result(output)

    @accounting.command("分类")
    async def show_categories(self, event: AstrMessageEvent):
        """查看支出分类统计"""
        user_id = event.get_sender_id()
        records = self.user_records.get(user_id, [])

        # 按分类统计支出
        category_stats = {}
        for record in records:
            if record["type"] == "expense":
                category = record["category"]
                category_stats[category] = category_stats.get(category, 0) + record["amount"]

        # 按金额排序
        sorted_categories = sorted(category_stats.items(), key=lambda x: x[1], reverse=True)

        # 构建输出
        output = f"📊 支出分类统计:\n"

        if not sorted_categories:
            output += "暂无支出记录\n"
        else:
            for category, amount in sorted_categories[:5]:  # 只显示前5个分类
                percentage = (amount / sum(category_stats.values())) * 100
                output += f"• {category}: {amount} ({percentage:.1f}%)\n"
            if len(sorted_categories) > 5:
                output += f"• ...等{len(sorted_categories)}个分类\n"

        yield event.plain_result(output)

    @accounting.command("收入分类")
    async def show_income_categories(self, event: AstrMessageEvent):
        """查看收入分类统计"""
        user_id = event.get_sender_id()
        records = self.user_records.get(user_id, [])

        # 按来源统计收入
        source_stats = {}
        for record in records:
            if record["type"] == "income":
                source = record["source"]
                source_stats[source] = source_stats.get(source, 0) + record["amount"]

        # 按金额排序
        sorted_sources = sorted(source_stats.items(), key=lambda x: x[1], reverse=True)

        # 构建输出
        output = f"📊 收入来源统计:\n"

        if not sorted_sources:
            output += "暂无收入记录\n"
        else:
            for source, amount in sorted_sources[:5]:  # 只显示前5个来源
                percentage = (amount / sum(source_stats.values())) * 100
                output += f"• {source}: {amount} ({percentage:.1f}%)\n"
            if len(sorted_sources) > 5:
                output += f"• ...等{len(sorted_sources)}个来源\n"

        yield event.plain_result(output)

    @accounting.command("删")
    async def delete_record(self, event: AstrMessageEvent, record_id: str):
        """删除指定记录"""
        user_id = event.get_sender_id()
        records = self.user_records.get(user_id, [])

        # 查找记录
        record_index = None
        for i, record in enumerate(records):
            if record["id"] == record_id:
                record_index = i
                break

        if record_index is None:
            yield event.plain_result(f"❌ 未找到记录ID为 '{record_id}' 的记录")
            return

        # 删除记录
        deleted_record = records.pop(record_index)

        # 保存数据
        self.save_data()

        # 返回确认信息
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(deleted_record["timestamp"]))
        yield event.plain_result(f"🗑️ 记录已删除\n"
                                f"ID: {deleted_record['id']}\n"
                                f"类型: {'支出' if deleted_record['type'] == 'expense' else '收入'}\n"
                                f"金额: {deleted_record['amount']}\n"
                                f"时间: {time_str}")

    # ===== 辅助方法 =====

    def add_record(self, user_id: str, record: Dict) -> None:
        """添加记录到用户的记录列表"""
        records = self.user_records.get(user_id, [])
        records.append(record)
        self.user_records[user_id] = records

    def generate_record_id(self, user_id: str) -> str:
        """生成唯一记录ID"""
        import uuid
        return str(uuid.uuid4())[:8]

    def load_data(self) -> None:
        """从文件加载数据"""
        try:
            if os.path.exists(self.data_path):
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    self.user_records = json.load(f)
        except Exception as e:
            logger.error(f"加载记账数据失败: {str(e)}")
            self.user_records = {}

    def save_data(self) -> None:
        """保存数据到文件"""
        try:
            with open(self.data_path, 'w', encoding='utf-8') as f:
                json.dump(self.user_records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存记账数据失败: {str(e)}")

    async def terminate(self):
        """插件卸载/停用时执行的清理操作"""
        # 保存数据
        self.save_data()
        logger.info("记账插件已卸载")
