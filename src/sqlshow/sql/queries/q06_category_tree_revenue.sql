-- title: Revenue up a category tree
-- question: What does each category earn, counting everything below it?
-- technique: two recursive CTEs (a path and a closure) over a self-referencing table
--
-- `paths` walks down from the roots building the readable path and the depth. `closure` lists every (ancestor,
-- descendant) pair, a category being its own descendant, so summing over it rolls each category's revenue up to all
-- its ancestors. Only leaf categories have products, so own_revenue is zero above them.
WITH RECURSIVE paths AS (
    SELECT category_id, name::text AS path, 0 AS depth
    FROM categories
    WHERE parent_id IS NULL
    UNION ALL
    SELECT c.category_id, p.path || ' > ' || c.name, p.depth + 1
    FROM paths AS p
    JOIN categories AS c ON c.parent_id = p.category_id
),
closure AS (
    SELECT category_id AS ancestor_id, category_id AS descendant_id
    FROM categories
    UNION ALL
    SELECT cl.ancestor_id, c.category_id
    FROM closure AS cl
    JOIN categories AS c ON c.parent_id = cl.descendant_id
),
own AS (
    SELECT category_id, SUM(amount) AS revenue
    FROM sales
    GROUP BY category_id
)
SELECT p.category_id,
       p.path,
       p.depth,
       COALESCE(o.revenue, 0) AS own_revenue,
       COALESCE(SUM(d.revenue), 0) AS total_revenue
FROM paths AS p
LEFT JOIN own AS o ON o.category_id = p.category_id
JOIN closure AS cl ON cl.ancestor_id = p.category_id
LEFT JOIN own AS d ON d.category_id = cl.descendant_id
GROUP BY p.category_id, p.path, p.depth, o.revenue
ORDER BY p.depth, p.category_id;
