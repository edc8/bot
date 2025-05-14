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
        # 用户账本数据结构: {用户ID: {账本名称: 账本数据}}
        self.user_books: Dict[str, Dict[str, Dict]] = {}
        # 插件数据存储路径
        self.data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounting_data.json")
        # 加载已保存的数据
        self.load_data()
        # 默认账本名称
        self.default_book_name = "默认账本"

    def get_user_books(self, user_id: str) -> Dict[str, Dict]:
        """获取用户的所有账本"""
        if user_id not in self.user_books:
            self.user_books[user_id] = {
                self.default_book_name: {
                    "current": True,
                    "records": []
                }
            }
        return self.user_books[user_id]

    def get_user_book(self, user_id: str, book_name: str) -> Dict:
        """获取用户的指定账本"""
        books = self.get_user_books(user_id)
        if book_name not in books:
            # 如果账本不存在，创建它
            books[book_name] = {
                "current": False,
                "records": []
            }
        return books[book_name]

    def get_current_book_name(self, user_id: str) -> str:
        """获取用户的当前账本名称"""
        books = self.get_user_books(user_id)
        for book_name, book_data in books.items():
            if book_data.get("current", False):
                return book_name
        # 如果没有当前账本，默认使用第一个账本
        return next(iter(books.keys()), self.default_book_name)

    def create_user_book(self, user_id: str, book_name: str) -> None:
        """创建新账本"""
        books = self.get_user_books(user_id)
        books[book_name] = {
            "current": True,
            "records": []
        }
        # 将其他账本标记为非当前
        for name in books:
            if name != book_name:
                books[name]["current"] = False

    def switch_user_book(self, user_id: str, book_name: str) -> None:
        """切换当前账本"""
        books = self.get_user_books(user_id)
        if book_name in books:
            # 将所有账本标记为非当前
            for name in books:
                books[name]["current"] = False
            # 将指定账本标记为当前
            books[book_name]["current"] = True

    def add_record(self, user_id: str, book_name: str, record: Dict) -> None:
        """添加记录到账本"""
        book = self.get_user_book(user_id, book_name)
        book["records"].append(record)

    def generate_record_id(self, user_id: str, book_name: str) -> str:
        """生成唯一记录ID"""
        import uuid
        return str(uuid.uuid4())[:8]

    def load_data(self) -> None:
        """从文件加载数据"""
        try:
            if os.path.exists(self.data_path):
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    self.user_books = json.load(f)
        except Exception as e:
            logger.error(f"加载记账数据失败: {str(e)}")
            self.user_books = {}

    def save_data(self) -> None:
        """保存数据到文件"""
        try:
            with open(self.data_path, 'w', encoding='utf-8') as f:
                json.dump(self.user_books, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存记账数据失败: {str(e)}")

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
            "/ac 记 [金额] [分类] [备注(可选)] - 添加支出\n"
            "/ac 收 [金额] [来源] [备注(可选)] - 添加收入\n"
            "/ac 查 - 查看最近10条记录\n"
            "/ac 汇总 - 查看账本汇总信息\n"
            "/ac 分类 - 查看支出分类统计\n"
            "/ac 删 [记录ID] - 删除记录\n"
            "/ac 账本 新建 [名称] - 创建新账本\n"
            "/ac 账本 切换 [名称] - 切换账本\n"
            "/ac 账本 列表 - 查看所有账本\n"
            "/ac 账本 删除 [名称] - 删除账本\n"
            "/ac 帮助 - 显示本帮助\n"
            "====================\n"
            "示例:\n"
            "/ac 记 25 餐饮 午餐\n"
            "/ac 收 5000 工资 6月工资"
        )
        yield event.plain_result(help_text)

    @accounting.command("记")
    async def record(self, event: AstrMessageEvent, amount: str, category: str, note: str = ""):
        """记录收支"""
        user_id = event.get_sender_id()
        book_name = self.get_current_book_name(user_id)

        try:
            amount_value = float(amount)
            if amount_value <= 0:
                raise ValueError("金额必须大于0")
        except ValueError as e:
            yield event.plain_result(f"错误: {str(e)}")
            return

        # 判断是收入还是支出
        is_income = category.startswith('+')
        if is_income:
            category = category[1:]  # 移除加号
            await self.add_income(event, amount, category, note)
        else:
            await self.add_expense(event, amount, category, note)

    @accounting.command("收")
    async def add_income(self, event: AstrMessageEvent, amount: str, source: str, note: str = ""):
        """添加收入记录"""
        user_id = event.get_sender_id()
        book_name = self.get_current_book_name(user_id)

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
        record_id = self.generate_record_id(user_id, book_name)
        record = {
            "id": record_id,
            "type": "income",
            "amount": amount_value,
            "source": source,
            "note": note,
            "timestamp": timestamp
        }

        # 添加到账本
        self.add_record(user_id, book_name, record)

        # 保存数据
        self.save_data()

        # 返回确认信息
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        yield event.plain_result(f"📝 收入记录已添加\n"
                                f"金额: {amount_value}\n"
                                f"来源: {source}\n"
                                f"备注: {note if note else '无'}\n"
                                f"时间: {time_str}\n"
                                f"账本: {book_name}")

    @accounting.command("查")
    async def list_records(self, event: AstrMessageEvent):
        """查看最近的记账记录"""
        user_id = event.get_sender_id()
        book_name = self.get_current_book_name(user_id)

        count_value = 10

        # 获取账本
        book = self.get_user_book(user_id, book_name)
        records = book.get("records", [])

        if not records:
            yield event.plain_result(f"📒 账本 '{book_name}' 中没有记录")
            return

        # 按时间倒序排列
        sorted_records = sorted(records, key=lambda x: x["timestamp"], reverse=True)

        # 限制数量
        recent_records = sorted_records[:count_value]

        # 构建输出
        output = f"📒 账本 '{book_name}' 的最近 {len(recent_records)} 条记录:\n"
        for record in recent_records:
            time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record["timestamp"]))
            if record["type"] == "expense":
                output += f"• [{record['id']}] 支出 {record['amount']} - {record['category']}"
                if record["note"]:
                    output += f" ({record['note']})"
                output += f" - {time_str}\n"
            else:
                output += f"• [{record['id']}] 收入 {record['amount']} - {record['source']}"
                if record["note"]:
                    output += f" ({record['note']})"
                output += f" - {time_str}\n"

        yield event.plain_result(output)

    @accounting.command("汇总")
    async def show_summary(self, event: AstrMessageEvent):
        """查看账本汇总信息"""
        user_id = event.get_sender_id()
        book_name = self.get_current_book_name(user_id)

        # 获取账本
        book = self.get_user_book(user_id, book_name)
        records = book.get("records", [])

        if not records:
            yield event.plain_result(f"📒 账本 '{book_name}' 中没有记录")
            return

        # 计算总收入、总支出和结余
        total_income = sum(record["amount"] for record in records if record["type"] == "income")
        total_expense = sum(record["amount"] for record in records if record["type"] == "expense")
        balance = total_income - total_expense

        # 按分类统计支出
        category_stats = {}
        for record in records:
            if record["type"] == "expense":
                category = record["category"]
                category_stats[category] = category_stats.get(category, 0) + record["amount"]

        # 按金额排序
        sorted_categories = sorted(category_stats.items(), key=lambda x: x[1], reverse=True)

        # 构建输出
        output = f"📊 账本 '{book_name}' 汇总信息:\n"
        output += f"📅 记录数量: {len(records)}\n"
        output += f"💵 总收入: {total_income}\n"
        output += f"💸 总支出: {total_expense}\n"
        output += f"📈 结余: {balance}\n\n"

        if sorted_categories:
            output += "📊 支出分类统计:\n"
            for category, amount in sorted_categories[:5]:  # 只显示前5个分类
                percentage = (amount / total_expense) * 100 if total_expense > 0 else 0
                output += f"• {category}: {amount} ({percentage:.1f}%)\n"
            if len(sorted_categories) > 5:
                output += f"• ...等{len(sorted_categories)}个分类\n"

        yield event.plain_result(output)

    @accounting.command("分类")
    async def show_categories(self, event: AstrMessageEvent):
        """查看支出分类统计"""
        user_id = event.get_sender_id()
        book_name = self.get_current_book_name(user_id)

        # 获取账本
        book = self.get_user_book(user_id, book_name)
        records = book.get("records", [])

        # 按分类统计支出
        category_stats = {}
        for record in records:
            if record["type"] == "expense":
                category = record["category"]
                category_stats[category] = category_stats.get(category, 0) + record["amount"]

        # 按金额排序
        sorted_categories = sorted(category_stats.items(), key=lambda x: x[1], reverse=True)

        # 构建输出
        output = f"📊 账本 '{book_name}' 支出分类统计:\n"

        if not sorted_categories:
            output += "暂无支出记录\n"
        else:
            for category, amount in sorted_categories[:5]:  # 只显示前5个分类
                percentage = (amount / sum(category_stats.values())) * 100
                output += f"• {category}: {amount} ({percentage:.1f}%)\n"
            if len(sorted_categories) > 5:
                output += f"• ...等{len(sorted_categories)}个分类\n"

        yield event.plain_result(output)

    @accounting.command("删")
    async def delete_record(self, event: AstrMessageEvent, record_id: str):
        """删除指定记录"""
        user_id = event.get_sender_id()
        book_name = self.get_current_book_name(user_id)

        # 获取账本
        book = self.get_user_book(user_id, book_name)
        records = book.get("records", [])

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

    @accounting.command("账本")
    async def book_management(self, event: AstrMessageEvent, subcommand: str = "", *args):
        """账本管理命令"""
        user_id = event.get_sender_id()

        if subcommand == "新建":
            # 创建新账本
            if not args:
                yield event.plain_result("❌ 请指定账本名称")
                return

            book_name = " ".join(args)

            if book_name in self.get_user_books(user_id):
                yield event.plain_result(f"❌ 账本 '{book_name}' 已存在")
                return

            self.create_user_book(user_id, book_name)
            self.save_data()
            yield event.plain_result(f"✅ 账本 '{book_name}' 已成功创建")

        elif subcommand == "切换":
            # 切换当前账本
            if not args:
                yield event.plain_result("❌ 请指定账本名称")
                return

            book_name = " ".join(args)

            if book_name not in self.get_user_books(user_id):
                yield event.plain_result(f"❌ 账本 '{book_name}' 不存在")
                return

            self.switch_user_book(user_id, book_name)
            self.save_data()
            yield event.plain_result(f"✅ 已切换到账本 '{book_name}'")

        elif subcommand == "列表":
            # 列出所有账本
            books = self.get_user_books(user_id)
            current_book = self.get_current_book_name(user_id)

            if not books:
                yield event.plain_result("📚 你还没有任何账本")
                return

            output = "📚 你的账本列表:\n"
            for book_name in books:
                marker = "👉" if book_name == current_book else "  "
                output += f"{marker} {book_name}\n"

            yield event.plain_result(output)

        elif subcommand == "删除":
            # 删除账本
            if not args:
                yield event.plain_result("❌ 请指定要删除的账本名称")
                return

            book_name = " ".join(args)

            if book_name not in self.get_user_books(user_id):
                yield event.plain_result(f"❌ 账本 '{book_name}' 不存在")
                return

            # 不能删除默认账本
            if book_name == self.default_book_name:
                yield event.plain_result(f"❌ 不能删除默认账本")
                return

            # 删除账本
            current_book = self.get_current_book_name(user_id)
            if book_name == current_book:
                # 如果删除
