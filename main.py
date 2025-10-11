from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("aabill", "author", "一个支持记账、查账、对账和删除账单的 AA 分账插件", "1.3.0", "repo url")
class AABillPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.bills = {}  # 用于存储账目，格式为 {"名字": 金额}

    def get_bill_by_name(self, name: str):
        """获取指定名字的账单，如果不存在返回None"""
        return self.bills.get(name, None)

    def update_bill(self, name: str, amount: float):
        """更新账单记录，如果名字不存在则添加"""
        if name not in self.bills:
            self.bills[name] = 0
        self.bills[name] += amount

    def format_bill_details(self):
        """返回格式化的账单详情字符串"""
        if not self.bills:
            return "目前没有记账记录！"
        total = sum(self.bills.values())
        bill_details = "\n".join([f"{name}: {amount:.2f} 元" for name, amount in self.bills.items()])
        return f"当前账目：\n{bill_details}\n\n总支出：{total:.2f} 元"

    @filter.command("aa")
    async def record_bill(self, event: AstrMessageEvent):
        """
        指令：/aa <名字> <金额>
        记录某人的支出金额
        """
        user_name = event.get_sender_name()
        message_str = event.message_str.strip()
        logger.info(f"用户 {user_name} 调用了记账指令: {message_str}")

        parts = message_str.split()

        # 检查参数
        if len(parts) < 2:
            yield event.plain_result("格式错误！正确的格式是 `/aa <名字> <金额>`，示例：`/aa 陈 100`")
            return
        
        name = parts[0]
        try:
            amount = float(parts[1])
        except ValueError:
            yield event.plain_result("金额必须是数字！")
            return

        # 更新账单
        self.update_bill(name, amount)
        yield event.plain_result(f"已记录{name}的支出：{amount:.2f}元！当前总支出为：{sum(self.bills.values()):.2f}元")

    @filter.command("查账")
    async def check_bill(self, event: AstrMessageEvent):
        """
        指令：/查账 [<名字>]
        如果没有提供名字，列出所有账单；如果提供名字，查询该人的账单
        """
        message_str = event.message_str.strip()
        name = message_str[2:].strip()  # 去掉指令"/查账"部分

        if name:
            bill = self.get_bill_by_name(name)
            if bill is not None:
                yield event.plain_result(f"{name}的账单：{bill:.2f} 元")
            else:
                yield event.plain_result(f"没有找到{name}的账单记录。")
        else:
            # 查询所有账单
            result = self.format_bill_details()
            yield event.plain_result(result)

    @filter.command("对账")
    async def settle_bill(self, event: AstrMessageEvent):
        """
        指令：/对账
        计算每人的分摊金额，以及谁需要补钱/收钱
        """
        if not self.bills:
            yield event.plain_result("目前没有记账记录，无法进行对账！")
            return

        total = sum(self.bills.values())
        average = total / len(self.bills)

        adjustments = {name: amount - average for name, amount in self.bills.items()}
        owe_list = [f"{name} 需补 {-balance:.2f} 元" for name, balance in adjustments.items() if balance < 0]
        receive_list = [f"{name} 应收 {balance:.2f} 元" for name, balance in adjustments.items() if balance > 0]

        result = f"总支出：{total:.2f} 元\n均摊后每人应支付：{average:.2f} 元\n\n"
        result += "应收款项：\n" + "\n".join(receive_list) + "\n" if receive_list else ""
        result += "需付款项：\n" + "\n".join(owe_list) + "\n" if owe_list else ""

        yield event.plain_result(result)

    @filter.command("删除账单")
    async def delete_bill(self, event: AstrMessageEvent):
        """
        指令：/删除账单 <名字>
        删除某个人的账单记录
        """
        message_str = event.message_str.strip()
        name = message_str[5:].strip()  # 去掉指令"/删除账单"部分

        if not name:
            yield event.plain_result("请提供需要删除账单的姓名，格式为 `/删除账单 <名字>`")
            return

        if name in self.bills:
            del self.bills[name]
            yield event.plain_result(f"已删除{name}的账单记录。")
        else:
            yield event.plain_result(f"没有找到{name}的账单记录。")

    @filter.command("帮助")
    async def show_help(self, event: AstrMessageEvent):
        """
        指令：/帮助
        列出所有可用指令及其使用方法
        """
        help_text = (
            "AA记账插件 - 使用方法：\n\n"
            "1. `/aa <名字> <金额>`：记录某人的支出。\n"
            "   示例：`/aa 陈 100`\n\n"
            "2. `/查账 [<名字>]`：查询账单。\n"
            "   - 不带名字时查询所有账单。\n"
            "   - 带名字时查询指定人的账单。\n"
            "   示例：`/查账 陈`\n\n"
            "3. `/对账`：计算均摊后每人的需付款或应收款。\n\n"
            "4. `/删除账单 <名字>`：删除某人的账单记录。\n"
            "   示例：`/删除账单 陈`\n\n"
            "5. `/帮助`：显示所有指令和使用方法。"
        )
        yield event.plain_result(help_text)

    async def terminate(self):
        logger.info("AA 记账插件已停用。")
